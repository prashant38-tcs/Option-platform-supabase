from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.dashboard_state import DashboardState
from app.core.broadcaster import EventBroadcaster
from app.core.llm_router import LLMRouter, LLMConfigurationError
from app.core.fyers_auth_helpers import extract_auth_code, AuthCodeParseError
from app.integrations.fyers_client import FyersClient, FyersAPIError
from app.integrations.moneycontrol_rss import MoneycontrolRSSClient
from app.models.enums import Underlying, TradingMode
from app.models.quant_config import QuantAgentConfig
from app.models.risk_schemas import RiskAgentConfig
from app.agents.performance_tracker import PerformanceTracker
from app.graph.workflow import build_graph, build_shared_agents_for_underlyings
from app.scheduler.cycle_scheduler import CycleScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

_UNDERLYING_BY_VALUE = {u.value: u for u in Underlying}


def _resolve_underlyings(raw_values: list[str]) -> listresolved = []
    for v in raw_values:
        if v not in _UNDERLYING_BY_VALUE:
            raise ValueError(f"Unknown underlying '{v}'. Valid values: {sorted(_UNDERLYING_BY_VALUE.keys())}")
        resolved.append(_UNDERLYING_BY_VALUE[v])
    return resolved


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    fyers_client = FyersClient(settings)
    session_file = Path(__file__).resolve().parent.parent / ".fyers_session.json"
    if fyers_client.load_session_from_file(session_file):
        logger.info("Loaded valid Fyers session from %s -- daily login already done for today.", session_file)
    else:
        logger.warning(
            "No valid Fyers session found at %s. Complete today's login via GET /api/fyers/login-url "
            "and POST /api/fyers/exchange -- until then, cycles will safely halt at the data-ingestion step.",
            session_file,
        )
    news_client = MoneycontrolRSSClient(settings.moneycontrol_rss_urls)

    try:
        llm_router: LLMRouter | None = LLMRouter(settings)
    except LLMConfigurationError as exc:
        logger.warning("LLM router not configured (%s) -- Sentiment agent will use neutral fallback only.", exc)
        llm_router = None

    dashboard_state = DashboardState(default_mode=TradingMode(settings.default_trading_mode))
    performance_tracker = PerformanceTracker()
    broadcaster = EventBroadcaster()

    underlyings = _resolve_underlyings(settings.scheduler_default_underlyings)
    quant_config = QuantAgentConfig()
    risk_config = RiskAgentConfig()

    agents_by_underlying = build_shared_agents_for_underlyings(
        underlyings=underlyings, fyers_client=fyers_client, llm_router=llm_router, news_client=news_client,
        quant_config=quant_config, risk_config=risk_config, risk_free_rate=settings.risk_free_rate,
        performance_tracker=performance_tracker,
    )

    graph = build_graph()
    shared_lock = asyncio.Lock()

    scheduler = CycleScheduler(
        compiled_graph=graph, agents_by_underlying=agents_by_underlying, mode_provider=dashboard_state.get_trading_mode,
        interval_seconds=settings.cycle_interval_seconds, market_hours_only=settings.market_hours_only,
        shared_risk_lock=shared_lock, broadcaster=broadcaster,
    )

    app.state.settings = settings
    app.state.fyers_client = fyers_client
    app.state.news_client = news_client
    app.state.llm_router = llm_router
    app.state.dashboard_state = dashboard_state
    app.state.performance_tracker = performance_tracker
    app.state.agents_by_underlying = agents_by_underlying
    app.state.scheduler = scheduler
    app.state.broadcaster = broadcaster
    app.state.underlyings = underlyings
    # All underlyings share ONE PositionStore instance -- grab it once
    # here so /api/positions can read it without needing to know which
    # underlying's WorkflowAgents to look through.
    app.state.position_store = next(iter(agents_by_underlying.values())).position_store

    logger.info("Starting scheduler for underlyings: %s | default trading mode: %s | market_hours_only: %s",
                [u.value for u in underlyings], settings.default_trading_mode, settings.market_hours_only)
    scheduler.start()

    try:
        yield
    finally:
        logger.info("Shutting down scheduler...")
        await scheduler.stop()
        await fyers_client.aclose()
        await news_client.aclose()
        if llm_router is not None:
            await llm_router.aclose()


app = FastAPI(title="Multi-Agent Options Trading Platform", lifespan=lifespan)

_cors_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_settings.cors_allowed_origins,
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


@app.get("/api/underlyings")
async def list_underlyings():
    return [u.value for u in app.state.underlyings]


@app.get("/api/scheduler/status")
async def get_scheduler_status():
    return app.state.scheduler.get_status().model_dump(mode="json")


@app.get("/api/scheduler/cycles/{underlying}")
async def get_recent_cycles(underlying: str, limit: int = 20):
    if underlying not in _UNDERLYING_BY_VALUE:
        raise HTTPException(400, f"Unknown underlying '{underlying}'")
    u = _UNDERLYING_BY_VALUE[underlying]
    cycles = app.state.scheduler.get_recent_cycles(u, n=limit)
    return [c.model_dump(mode="json") for c in cycles]


class TradingModeUpdate(BaseModel):
    mode: str


@app.post("/api/scheduler/mode/{underlying}")
async def set_trading_mode(underlying: str, body: TradingModeUpdate):
    if underlying not in _UNDERLYING_BY_VALUE:
        raise HTTPException(400, f"Unknown underlying '{underlying}'")
    try:
        mode = TradingMode(body.mode)
    except ValueError:
        raise HTTPException(400, f"Invalid trading mode '{body.mode}'")
    app.state.dashboard_state.set_trading_mode(_UNDERLYING_BY_VALUE[underlying], mode)
    return {"underlying": underlying, "mode": mode.value}


@app.post("/api/scheduler/run-now/{underlying}")
async def run_now(underlying: str):
    if underlying not in _UNDERLYING_BY_VALUE:
        raise HTTPException(400, f"Unknown underlying '{underlying}'")
    u = _UNDERLYING_BY_VALUE[underlying]
    summary = await app.state.scheduler.run_now(u)
    return summary.model_dump(mode="json")


class CapitalUpdate(BaseModel):
    capital: float


@app.post("/api/capital")
async def set_capital(body: CapitalUpdate):
    try:
        app.state.dashboard_state.set_capital_override(body.capital)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    for agents in app.state.agents_by_underlying.values():
        agents.risk._config.manual_capital_override = body.capital  # noqa: SLF001
    return {"capital": body.capital}


@app.get("/api/positions")
async def get_open_positions():
    """Lists every currently OPEN Paper/Live position. Positions now
    close automatically at expiry (see risk_manager_agent.py's
    close_expired_positions_for_underlying, invoked at the start of every
    cycle) -- until a position's expiry date arrives, it stays open here
    and correctly counts against the max-concurrent-positions cap."""
    store = app.state.position_store
    positions = []
    for pos in store.all():
        signal = pos.signal
        positions.append({
            "position_id": pos.position_id,
            "underlying": pos.underlying.value,
            "trading_mode": pos.trading_mode.value,
            "strategy_type": signal.strategy_type.value,
            "risk_category": signal.risk_category.value,
            "opened_at": pos.opened_at.isoformat(),
            "expiry": signal.legs[0].expiry.isoformat() if signal.legs else None,
            "net_premium": signal.net_premium,
            "max_loss_estimate": signal.max_loss_estimate,
            "max_profit_estimate": signal.max_profit_estimate,
            "legs": [
                {"strike": leg.strike, "option_type": leg.option_type.value, "side": leg.side,
                 "lots": leg.lots, "entry_price": leg.entry_price_hint}
                for leg in signal.legs
            ],
        })
    return {"count": len(positions), "positions": positions}


@app.get("/api/fyers/session-status")
async def fyers_session_status():
    fyers_client: FyersClient = app.state.fyers_client
    return {"has_valid_session": fyers_client.has_valid_session(),
            "hint": ("Session valid for today." if fyers_client.has_valid_session()
                      else "No valid session -- complete today's login (see /api/fyers/login-url).")}


@app.get("/api/fyers/login-url")
async def fyers_login_url():
    fyers_client: FyersClient = app.state.fyers_client
    try:
        return {"login_url": fyers_client.build_login_url()}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


class FyersExchangeRequest(BaseModel):
    input: str


@app.post("/api/fyers/exchange")
async def fyers_exchange(body: FyersExchangeRequest):
    fyers_client: FyersClient = app.state.fyers_client
    try:
        auth_code = extract_auth_code(body.input)
    except AuthCodeParseError as exc:
        raise HTTPException(400, str(exc))

    try:
        session = await fyers_client.exchange_auth_code_for_token(auth_code)
    except FyersAPIError as exc:
        raise HTTPException(400, f"Fyers rejected the auth_code exchange: {exc}")

    session_file = Path(__file__).resolve().parent.parent / ".fyers_session.json"
    fyers_client.save_session_to_file(session_file)

    return {
        "success": True, "app_id": session.app_id, "is_compliant_app": session.is_compliant_app,
        "static_ip_whitelisted": session.static_ip_whitelisted,
        "valid_until": session.expires_at_market_close.isoformat() if session.expires_at_market_close else None,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/cycles/{underlying}")
async def ws_cycle_stream(websocket: WebSocket, underlying: str):
    if underlying not in _UNDERLYING_BY_VALUE:
        await websocket.close(code=4000, reason=f"Unknown underlying '{underlying}'")
        return

    u = _UNDERLYING_BY_VALUE[underlying]
    broadcaster: EventBroadcaster = websocket.app.state.broadcaster

    await websocket.accept()
    queue = await broadcaster.subscribe(u)

    try:
        status = websocket.app.state.scheduler.get_status()
        underlying_status = next((s for s in status.underlyings if s.underlying == u), None)
        await websocket.send_json({
            "type": "connected", "underlying": underlying,
            "scheduler_status": underlying_status.model_dump(mode="json") if underlying_status else None,
        })

        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected from %s stream", underlying)
    finally:
        await broadcaster.unsubscribe(u, queue)
