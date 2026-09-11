from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

from app.core.black_scholes import compute_full_greeks, to_computed_greeks, time_to_expiry_years
from app.core.market_calendar import now_ist_naive
from app.integrations.fyers_client import FyersClient, FyersSessionExpiredError, FyersAPIError
from app.integrations.moneycontrol_rss import MoneycontrolRSSClient
from app.models.enums import Underlying, OptionType
from app.models.fyers_schemas import FyersOptionChainResponse
from app.models.market_schemas import OptionChainItem, OptionChainSnapshot, UnderlyingQuote
from app.models.agent_state import TradingWorkflowState

logger = logging.getLogger("data_ingestion_agent")
AGENT_NAME = "DataIngestionAgent"

_UNDERLYING_INDEX_SYMBOL: dict[Underlying, str] = {
    Underlying.NIFTY: "NSE:NIFTY50-INDEX",
    Underlying.BANKNIFTY: "NSE:NIFTYBANK-INDEX",
    Underlying.FINNIFTY: "NSE:FINNIFTY-INDEX",
    Underlying.SENSEX: "BSE:SENSEX-INDEX",
}


class DataIngestionError(RuntimeError):
    pass


class DataIngestionAgent:
    def __init__(self, fyers_client: FyersClient, news_client: Optional[MoneycontrolRSSClient], risk_free_rate: float):
        self._fyers = fyers_client
        self._news = news_client
        self._risk_free_rate = risk_free_rate

    def _index_symbol(self, underlying: Underlying) -> str:
        if underlying not in _UNDERLYING_INDEX_SYMBOL:
            raise DataIngestionError(f"No Fyers index symbol mapped for {underlying}")
        return _UNDERLYING_INDEX_SYMBOL[underlying]

    async def fetch_option_chain_snapshot(
        self, underlying: Underlying, now: datetime, expiry_timestamp: Optional[str] = None, strike_count: int = 20
    ) -> OptionChainSnapshot:
        symbol = self._index_symbol(underlying)
        raw: FyersOptionChainResponse = await self._fyers.get_option_chain(
            symbol=symbol, strike_count=strike_count, timestamp=expiry_timestamp
        )

        # IMPORTANT: Fyers' real /data/options-chain-v3 response nests
        # everything (optionsChain, expiryData, indiavixData, callOi,
        # putOi) inside a top-level "data" object -- confirmed directly
        # against Fyers' own official API documentation sample response.
        # Every field below is read via raw.data.<field>, never raw.<field>
        # directly, for exactly this reason.
        options_chain = raw.data.optionsChain
        expiry_data = raw.data.expiryData
        india_vix_data = raw.data.indiavixData

        logger.info(
            "Fetched optionsChain for %s: %d legs, %d expiryData entries.",
            symbol, len(options_chain), len(expiry_data),
        )

        spot_leg = next((leg for leg in options_chain if leg.is_underlying_row()), None)

        spot_ltp: Optional[float] = None
        if spot_leg is not None:
            spot_ltp = spot_leg.ltp
        else:
            logger.warning(
                "No underlying spot row found in optionsChain for %s (chain had %d legs). "
                "Falling back to /data/quotes for spot price.",
                symbol, len(options_chain),
            )
            try:
                quotes_data = await self._fyers.get_quotes([symbol])
                entries = quotes_data.get("d", [])
                if entries:
                    v = entries[0].get("v", {})
                    spot_ltp = v.get("lp") or v.get("ltp") or v.get("last_price")
            except Exception as exc:
                logger.warning("Fallback /data/quotes call for %s also failed: %s", symbol, exc)

            if spot_ltp is None or spot_ltp <= 0:
                raise DataIngestionError(
                    f"Fyers option chain response for {symbol} did not include an underlying spot row, "
                    f"and the /data/quotes fallback also failed to yield a usable price."
                )

        expiry = self._resolve_expiry(expiry_data, expiry_timestamp, now)

        calls: list[OptionChainItem] = []
        puts: list[OptionChainItem] = []
        for leg in options_chain:
            if leg.is_underlying_row():
                continue
            is_call = leg.option_type == "CE"
            t = time_to_expiry_years(now, expiry)
            if t <= 0 or leg.ltp <= 0:
                continue
            bs_result = compute_full_greeks(leg.ltp, spot_ltp, leg.strike_price, now, expiry, self._risk_free_rate, is_call)
            greeks = to_computed_greeks(bs_result, self._risk_free_rate, t)
            item = OptionChainItem(
                underlying=underlying, expiry=expiry, strike=leg.strike_price,
                option_type=OptionType.CE if is_call else OptionType.PE,
                symbol=leg.symbol, ltp=leg.ltp, bid=leg.bid, ask=leg.ask,
                volume=leg.volume, open_interest=leg.oi, oi_change=leg.oich,
                oi_change_pct=leg.oichp, greeks=greeks,
            )
            (calls if is_call else puts).append(item)

        if not calls or not puts:
            raise DataIngestionError(f"Fyers option chain for {symbol} returned no usable priced legs")

        prev_close = spot_ltp
        spot_quote = UnderlyingQuote(
            underlying=underlying, ltp=spot_ltp, prev_close=prev_close, change=0.0,
            change_pct=0.0, timestamp=now, india_vix=india_vix_data.ltp if india_vix_data else None,
        )

        return OptionChainSnapshot(underlying=underlying, expiry=expiry, spot=spot_quote, calls=calls, puts=puts, fetched_at=now)

    @staticmethod
    def _resolve_expiry(expiry_data: list[dict], expiry_timestamp: Optional[str], now: datetime) -> datetime:
        if expiry_timestamp:
            try:
                return datetime.fromtimestamp(int(expiry_timestamp))
            except (ValueError, OverflowError):
                pass

        if expiry_data:
            first = expiry_data[0]
            for key in ("expiry", "date", "exp", "expiryDate", "expTs"):
                ts = first.get(key) if isinstance(first, dict) else None
                if ts is None:
                    continue
                try:
                    return datetime.fromtimestamp(int(ts))
                except (ValueError, TypeError, OverflowError):
                    pass
                if isinstance(ts, str):
                    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y", "%d%b%y"):
                        try:
                            return datetime.strptime(ts, fmt)
                        except ValueError:
                            continue

        raise DataIngestionError(
            "Could not resolve a concrete expiry datetime from the Fyers option chain response "
            "-- refusing to guess, since an incorrect expiry corrupts every downstream Greeks calculation. "
            f"Raw expiryData was: {expiry_data}"
        )

    async def fetch_news_headlines(self, max_items_per_feed: int = 20) -> list:
        if self._news is None:
            return []
        return await self._news.fetch_all(max_items_per_feed=max_items_per_feed)


async def data_ingestion_node(state: TradingWorkflowState, agent: DataIngestionAgent) -> TradingWorkflowState:
    now = now_ist_naive()

    try:
        snapshot = await agent.fetch_option_chain_snapshot(state.underlying, now)
        state.option_chain_snapshot = snapshot
        state.log(AGENT_NAME, f"Fetched option chain: {len(snapshot.calls)} calls / {len(snapshot.puts)} puts, "
                   f"spot={snapshot.spot.ltp:.2f}, ATM={snapshot.atm_strike}", level="info")
    except FyersSessionExpiredError as exc:
        state.data_ingestion_errors.append(str(exc))
        state.cycle_status = "halted"
        state.halt_or_error_reason = f"Fyers session expired: {exc}"
        state.log(AGENT_NAME, f"HALTED: Fyers session expired -- {exc}", level="error")
        return state
    except (FyersAPIError, DataIngestionError) as exc:
        state.data_ingestion_errors.append(str(exc))
        state.cycle_status = "halted"
        state.halt_or_error_reason = f"Data ingestion failed: {exc}"
        state.log(AGENT_NAME, f"HALTED: option chain fetch failed -- {exc}", level="error")
        return state

    try:
        headlines = await agent.fetch_news_headlines()
        state.recent_headlines = headlines
        state.log(AGENT_NAME, f"Fetched {len(headlines)} news headlines from Moneycontrol RSS", level="info")
    except Exception as exc:
        state.data_ingestion_errors.append(f"News fetch failed (non-fatal): {exc}")
        state.log(AGENT_NAME, f"News fetch failed (continuing without sentiment input): {exc}", level="warning")

    return state
