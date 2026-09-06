from __future__ import annotations
import logging
import uuid
from datetime import datetime
from typing import Optional

from app.integrations.fyers_client import FyersClient, FyersAPIError, FyersSessionExpiredError
from app.core.market_calendar import now_ist_naive
from app.agents.risk_manager_agent import RiskManagerAgent
from app.models.enums import TradingMode, OrderLifecycleStatus, FyersOrderType, FyersProductType
from app.models.fyers_schemas import FyersMultiLegOrderRequest, FyersMultiLegOrderLeg
from app.models.risk_schemas import LiveComplianceChecklist
from app.models.strategy_schemas import TradeSignal, ManagedOrder
from app.models.agent_state import TradingWorkflowState

logger = logging.getLogger("execution_agent")
AGENT_NAME = "ExecutionAgent"


class ExecutionAgent:
    def __init__(self, fyers_client: Optional[FyersClient], risk_agent: RiskManagerAgent,
                 compliance_checklist: Optional[LiveComplianceChecklist] = None, algo_id_tag: Optional[str] = None):
        self._fyers = fyers_client
        self._risk_agent = risk_agent
        self._compliance_checklist = compliance_checklist
        self._algo_id_tag = algo_id_tag

    async def execute(self, signal: TradeSignal, trading_mode: TradingMode, now: datetime) -> ManagedOrder:
        if trading_mode == TradingMode.ADVISORY:
            return self._execute_advisory(signal, now)
        if trading_mode == TradingMode.PAPER:
            return self._execute_paper(signal, now)
        if trading_mode == TradingMode.LIVE:
            return await self._execute_live(signal, now)
        raise ValueError(f"Unknown trading mode: {trading_mode}")

    def _execute_advisory(self, signal: TradeSignal, now: datetime) -> ManagedOrder:
        return ManagedOrder(order_id=f"adv-{uuid.uuid4().hex[:10]}", signal_id=signal.signal_id,
                              trading_mode=TradingMode.ADVISORY, status=OrderLifecycleStatus.ADVISORY_ONLY,
                              created_at=now, updated_at=now, symbol=signal.legs[0].symbol if signal.legs else "",
                              side=signal.legs[0].side if signal.legs else None, product_type=FyersProductType.MARGIN,
                              quantity=sum(leg.total_quantity for leg in signal.legs),
                              limit_price=signal.legs[0].entry_price_hint if signal.legs else 0.0)

    def _execute_paper(self, signal: TradeSignal, now: datetime) -> ManagedOrder:
        self._risk_agent.record_position_opened(delta=signal.net_delta, vega=signal.net_vega)
        return ManagedOrder(order_id=f"paper-{uuid.uuid4().hex[:10]}", signal_id=signal.signal_id,
                              trading_mode=TradingMode.PAPER, status=OrderLifecycleStatus.SIMULATED_OPEN,
                              created_at=now, updated_at=now, symbol=signal.legs[0].symbol if signal.legs else "",
                              side=signal.legs[0].side if signal.legs else None, product_type=FyersProductType.MARGIN,
                              quantity=sum(leg.total_quantity for leg in signal.legs),
                              limit_price=signal.legs[0].entry_price_hint if signal.legs else 0.0,
                              filled_price=signal.legs[0].entry_price_hint if signal.legs else 0.0)

    async def _execute_live(self, signal: TradeSignal, now: datetime) -> ManagedOrder:
        base_order = ManagedOrder(order_id=f"live-{uuid.uuid4().hex[:10]}", signal_id=signal.signal_id,
                                    trading_mode=TradingMode.LIVE, status=OrderLifecycleStatus.PENDING_RISK_CHECK,
                                    created_at=now, updated_at=now, symbol=signal.legs[0].symbol if signal.legs else "",
                                    side=signal.legs[0].side if signal.legs else None, product_type=FyersProductType.MARGIN,
                                    quantity=sum(leg.total_quantity for leg in signal.legs),
                                    limit_price=signal.legs[0].entry_price_hint if signal.legs else 0.0,
                                    order_tag_algo_id=self._algo_id_tag)

        if self._fyers is None:
            base_order.status = OrderLifecycleStatus.ERRORED
            base_order.error_message = "LIVE mode requires a configured FyersClient -- none provided."
            return base_order

        if self._compliance_checklist is None or not self._compliance_checklist.all_complete():
            can_arm, missing = self._risk_agent.can_arm_live_trading(self._compliance_checklist or _empty_checklist())
            base_order.status = OrderLifecycleStatus.REJECTED_BY_RISK
            base_order.error_message = f"LIVE trading blocked -- compliance checklist incomplete. Missing: {', '.join(missing)}"
            logger.warning("LIVE order for %s blocked: %s", signal.signal_id, base_order.error_message)
            return base_order

        if self._risk_agent.should_force_flatten():
            base_order.status = OrderLifecycleStatus.REJECTED_BY_RISK
            base_order.error_message = "Daily loss circuit breaker is tripped -- no new LIVE orders permitted."
            return base_order

        multileg_request = FyersMultiLegOrderRequest(orderTag=self._algo_id_tag, legs=[
            FyersMultiLegOrderLeg(symbol=leg.symbol, qty=leg.total_quantity, side=leg.side,
                                    type=FyersOrderType.MARKET, limitPrice=0.0, productType=FyersProductType.MARGIN)
            for leg in signal.legs
        ])

        try:
            response = await self._fyers.place_multileg_order(multileg_request)
        except FyersSessionExpiredError as exc:
            base_order.status = OrderLifecycleStatus.ERRORED
            base_order.error_message = f"Fyers session expired during order placement: {exc}"
            return base_order
        except FyersAPIError as exc:
            base_order.status = OrderLifecycleStatus.BROKER_REJECTED
            base_order.error_message = str(exc)
            return base_order

        if response.get("s") == "ok":
            base_order.status = OrderLifecycleStatus.SENT_TO_BROKER
            base_order.broker_order_id = str(response.get("id", ""))
            self._risk_agent.record_position_opened(delta=signal.net_delta, vega=signal.net_vega)
        else:
            base_order.status = OrderLifecycleStatus.BROKER_REJECTED
            base_order.error_message = response.get("message", "Unknown broker error")

        return base_order


def _empty_checklist() -> LiveComplianceChecklist:
    from app.models.risk_schemas import ComplianceChecklistItem
    empty = lambda k, l: ComplianceChecklistItem(key=k, label=l, is_complete=False)
    return LiveComplianceChecklist(
        static_ip_whitelisted=empty("ip", "Static IP whitelisted"), compliant_app_activated=empty("app", "Compliant Fyers App activated"),
        daily_2fa_flow_tested=empty("2fa", "Daily 2FA flow tested"), order_rate_under_10_per_sec_confirmed=empty("rate", "Order rate under 10/sec confirmed"),
        algo_id_tagging_wired=empty("algoid", "Algo-ID tagging wired"), manual_arm_toggle_confirmed=empty("arm", "Manual arm toggle confirmed"),
    )


_WARNING_STATUSES = {OrderLifecycleStatus.ERRORED.value, OrderLifecycleStatus.BROKER_REJECTED.value, OrderLifecycleStatus.REJECTED_BY_RISK.value}


async def execution_node(state: TradingWorkflowState, agent: ExecutionAgent) -> TradingWorkflowState:
    now = now_ist_naive()
    if state.cycle_status == "halted":
        state.log(AGENT_NAME, "Skipping execution -- cycle already halted upstream.", level="warning")
        return state

    for signal in state.approved_signals:
        order = await agent.execute(signal, state.trading_mode, now)
        state.orders_created.append(order)
        status_str = order.status
        state.log(AGENT_NAME, f"[{state.trading_mode.value}] {signal.strategy_type.value} -> order {order.order_id} "
                   f"status={status_str}" + (f" | {order.error_message}" if order.error_message else ""),
                   level="info" if status_str not in _WARNING_STATUSES else "warning")

    state.cycle_status = "completed"
    state.completed_at = now
    return state
