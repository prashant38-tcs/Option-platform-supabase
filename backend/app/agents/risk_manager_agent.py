from __future__ import annotations
import logging
from datetime import datetime, time as dtime
from typing import Optional

from app.integrations.fyers_client import FyersClient, FyersSessionExpiredError
from app.core.market_calendar import now_ist_naive
from app.core.position_store import PositionStore, compute_position_realized_pnl, is_position_expired
from app.models.enums import TradingMode, FyersOrderSide, RiskCategory
from app.models.risk_schemas import RiskAgentConfig, DailyRiskState, LiveComplianceChecklist
from app.models.strategy_schemas import TradeSignal, RiskReview
from app.models.agent_state import TradingWorkflowState

logger = logging.getLogger("risk_manager_agent")
AGENT_NAME = "RiskManagerAgent"


class RiskManagerAgent:
    def __init__(self, config: RiskAgentConfig, fyers_client):
        self._config = config
        self._fyers = fyers_client
        self._daily_state: DailyRiskState | None = None

    async def refresh_daily_state(self, now: datetime) -> DailyRiskState:
        capital_base: float
        try:
            funds = await self._fyers.get_funds()
            capital_base = funds.available_balance()
            source = "fyers_live"
        except FyersSessionExpiredError:
            logger.warning("Fyers session expired during risk capital refresh -- using manual override if set")
            capital_base = self._config.manual_capital_override or 0.0
            source = "manual_override_fallback_session_expired"
        except Exception as exc:
            logger.warning("Fyers funds fetch failed (%s) -- using manual override if set", exc)
            capital_base = self._config.manual_capital_override or 0.0
            source = "manual_override_fallback_error"

        if capital_base <= 0 and self._config.manual_capital_override:
            capital_base = self._config.manual_capital_override
            source = "manual_override"

        if capital_base <= 0:
            raise ValueError(
                "No usable capital figure available: Fyers funds call failed AND no "
                "manual_capital_override is set. Cannot evaluate risk without a capital base."
            )

        prior = self._daily_state
        is_new_day = prior is None or prior.trading_date.date() != now.date()

        target_amount = capital_base * (self._config.daily_profit_target_pct / 100.0)
        max_loss_amount = capital_base * (self._config.daily_max_loss_pct / 100.0)

        self._daily_state = DailyRiskState(
            trading_date=now, capital_base=capital_base,
            daily_profit_target_amount=target_amount, daily_max_loss_amount=max_loss_amount,
            realized_pnl_today=0.0 if is_new_day else prior.realized_pnl_today,
            unrealized_pnl_today=0.0 if is_new_day else prior.unrealized_pnl_today,
            open_positions_count=0 if prior is None else prior.open_positions_count,
            current_portfolio_delta=0.0 if prior is None else prior.current_portfolio_delta,
            current_portfolio_vega=0.0 if prior is None else prior.current_portfolio_vega,
        )
        logger.info("Risk state refreshed: capital_base=%.2f (source=%s), profit_target=%.2f, max_loss=%.2f",
                    capital_base, source, target_amount, max_loss_amount)
        return self._daily_state

    @property
    def daily_state(self) -> DailyRiskState:
        if self._daily_state is None:
            raise RuntimeError("refresh_daily_state() must be called before evaluating any signal")
        return self._daily_state

    def review_signal(self, signal: TradeSignal, now: datetime) -> RiskReview:
        state = self.daily_state
        reasons: list[str] = []

        if state.loss_circuit_breaker_tripped:
            reasons.append(f"Daily max loss circuit breaker already tripped "
                            f"(PnL {state.total_pnl_today:.2f} <= -{state.daily_max_loss_amount:.2f})")
        if state.profit_target_hit and self._config.lock_in_profit_on_target_hit:
            reasons.append(f"Daily profit target already reached "
                            f"(PnL {state.total_pnl_today:.2f} >= {state.daily_profit_target_amount:.2f}); "
                            f"locking in gains, no new entries today")

        if state.open_positions_count >= self._config.max_concurrent_positions:
            reasons.append(f"Max concurrent positions reached "
                            f"({state.open_positions_count}/{self._config.max_concurrent_positions})")

        capital_at_risk = self._estimate_capital_at_risk(signal)
        capital_at_risk_pct = (capital_at_risk / state.capital_base * 100.0) if state.capital_base > 0 else 100.0

        applicable_cap = (
            self._config.naked_strategy_max_margin_per_position_pct
            if signal.risk_category == RiskCategory.UNDEFINED_RISK
            else self._config.max_margin_per_position_pct
        )
        if capital_at_risk_pct > applicable_cap:
            cap_label = "naked-strategy margin cap" if signal.risk_category == RiskCategory.UNDEFINED_RISK else "defined-risk margin cap"
            reasons.append(f"Capital at risk {capital_at_risk_pct:.2f}% exceeds {cap_label} of {applicable_cap:.2f}% per position")

        capital_in_lakhs = max(state.capital_base / 100_000.0, 0.01)
        max_delta = self._config.max_portfolio_delta_per_lakh_capital * capital_in_lakhs
        max_vega = self._config.max_portfolio_vega_per_lakh_capital * capital_in_lakhs

        projected_delta = state.current_portfolio_delta + signal.net_delta
        projected_vega = state.current_portfolio_vega + signal.net_vega

        if abs(projected_delta) > max_delta:
            reasons.append(f"Projected portfolio delta {projected_delta:.2f} would exceed limit ±{max_delta:.2f} (scaled to capital)")
        if abs(projected_vega) > max_vega:
            reasons.append(f"Projected portfolio vega {projected_vega:.2f} would exceed limit ±{max_vega:.2f} (scaled to capital)")

        is_zero_or_near_dte = self._is_zero_or_near_dte(signal, now)
        if is_zero_or_near_dte and self._config.block_new_entries_on_expiry_day and not self._config.allow_zero_dte_override:
            reasons.append(f"Expiry-day entry blocked (cutoff {self._config.expiry_day_cutoff_time.isoformat()} IST); "
                            f"set allow_zero_dte_override=True to permit explicitly")

        approved = len(reasons) == 0

        return RiskReview(
            signal_id=signal.signal_id, reviewed_at=now, approved=approved, rejection_reasons=reasons,
            capital_at_risk=capital_at_risk, capital_at_risk_pct_of_equity=round(capital_at_risk_pct, 3),
            projected_portfolio_delta_after=round(projected_delta, 2), projected_portfolio_vega_after=round(projected_vega, 2),
            daily_pnl_at_review_time=state.total_pnl_today, daily_loss_circuit_breaker_tripped=state.loss_circuit_breaker_tripped,
            daily_profit_target_reached=state.profit_target_hit, is_zero_or_near_dte=is_zero_or_near_dte,
            notes="Deterministic rule-based evaluation -- no LLM involved in this decision.",
        )

    def record_position_opened(self, delta: float, vega: float) -> None:
        state = self.daily_state
        state.open_positions_count += 1
        state.current_portfolio_delta += delta
        state.current_portfolio_vega += vega

    def record_position_closed(self, realized_pnl: float, delta: float, vega: float) -> None:
        state = self.daily_state
        state.open_positions_count = max(0, state.open_positions_count - 1)
        state.current_portfolio_delta -= delta
        state.current_portfolio_vega -= vega
        state.realized_pnl_today += realized_pnl

    def can_arm_live_trading(self, checklist: LiveComplianceChecklist) -> tuple[bool, list[str]]:
        missing = []
        for field_name, item in checklist.model_dump().items():
            if isinstance(item, dict) and not item.get("is_complete", False):
                missing.append(item.get("label", field_name))
        return (len(missing) == 0, missing)

    def should_force_flatten(self) -> bool:
        return self.daily_state.loss_circuit_breaker_tripped

    def _estimate_capital_at_risk(self, signal: TradeSignal) -> float:
        if signal.max_loss_estimate is not None:
            return abs(signal.max_loss_estimate)
        total = 0.0
        for leg in signal.legs:
            if leg.side == FyersOrderSide.BUY:
                total += abs(leg.entry_price_hint) * leg.total_quantity
            else:
                notional = leg.strike * leg.total_quantity
                total += notional * (self._config.naked_short_margin_pct_of_notional / 100.0)
        return round(total, 2)

    @staticmethod
    def _is_zero_or_near_dte(signal: TradeSignal, now: datetime) -> bool:
        for leg in signal.legs:
            if leg.expiry.date() == now.date():
                return True
        return False


def close_expired_positions_for_underlying(
    risk_agent: RiskManagerAgent, position_store: PositionStore, underlying, now: datetime,
    current_spot: Optional[float],
) -> list"""Closes every OPEN position for `underlying` whose legs have reached
    expiry, crediting the realized P&L (marked to intrinsic value at the
    current spot) back into the shared RiskManagerAgent's daily state and
    freeing the position slot. This did not exist anywhere in the
    live/paper cycle path before -- only the backtest engine had
    expiry-based closing logic -- which is why positions opened during
    testing never closed and permanently filled the concurrent-position cap."""
    messages: list[str] = []
    if current_spot is None:
        return messages

    for position in position_store.for_underlying(underlying):
        if not is_position_expired(position.signal, now):
            continue
        realized_pnl = compute_position_realized_pnl(position.signal, current_spot)
        risk_agent.record_position_closed(
            realized_pnl=realized_pnl, delta=position.signal.net_delta, vega=position.signal.net_vega,
        )
        position_store.remove(position.position_id)
        messages.append(
            f"Closed expired position {position.position_id} ({position.signal.strategy_type.value}) "
            f"at spot {current_spot:.2f} -- realized P&L Rs.{realized_pnl:,.2f}"
        )
    return messages


async def risk_manager_node(state: TradingWorkflowState, agent: RiskManagerAgent, position_store: Optional[PositionStore] = None) -> TradingWorkflowState:
    now = now_ist_naive()
    try:
        daily_state = await agent.refresh_daily_state(now)
    except ValueError as exc:
        state.cycle_status = "halted"
        state.halt_or_error_reason = str(exc)
        state.log(AGENT_NAME, f"HALTED: {exc}", level="error")
        return state

    state.daily_risk_state = daily_state

    if position_store is not None:
        current_spot = state.option_chain_snapshot.spot.ltp if state.option_chain_snapshot else None
        close_messages = close_expired_positions_for_underlying(agent, position_store, state.underlying, now, current_spot)
        for msg in close_messages:
            state.log(AGENT_NAME, msg, level="decision")

    state.log(AGENT_NAME,
              f"Capital base refreshed: Rs.{daily_state.capital_base:,.2f} | "
              f"Target: Rs.{daily_state.daily_profit_target_amount:,.2f} | "
              f"Max loss: Rs.{daily_state.daily_max_loss_amount:,.2f} | "
              f"PnL today: Rs.{daily_state.total_pnl_today:,.2f}", level="info")

    if agent.should_force_flatten():
        state.log(AGENT_NAME, "DAILY LOSS CIRCUIT BREAKER TRIPPED -- forcing flatten, no new entries.", level="decision")
        state.cycle_status = "halted"
        state.halt_or_error_reason = "daily_max_loss_circuit_breaker_tripped"
        return state

    for signal in state.candidate_signals:
        review = agent.review_signal(signal, now)
        state.risk_reviews.append(review)
        if review.approved:
            state.approved_signals.append(signal)
            state.log(AGENT_NAME, f"APPROVED signal {signal.signal_id} ({signal.strategy_type})", level="decision")
        else:
            state.log(AGENT_NAME, f"REJECTED signal {signal.signal_id}: {'; '.join(review.rejection_reasons)}", level="decision")

    return 
