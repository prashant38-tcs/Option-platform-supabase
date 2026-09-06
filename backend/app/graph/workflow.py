from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional, Any

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig

from app.core.llm_router import LLMRouter
from app.core.volatility_analytics import IVHistoryBuffer
from app.integrations.fyers_client import FyersClient
from app.integrations.moneycontrol_rss import MoneycontrolRSSClient
from app.agents.data_ingestion_agent import DataIngestionAgent, data_ingestion_node
from app.agents.sentiment_agent import SentimentAgent, sentiment_node
from app.agents.quant_analytics_agent import QuantAnalyticsAgent, quant_analytics_node
from app.agents.risk_manager_agent import RiskManagerAgent, risk_manager_node
from app.agents.execution_agent import ExecutionAgent, execution_node
from app.agents.performance_tracker import PerformanceTracker
from app.models.agent_state import TradingWorkflowState
from app.models.quant_config import QuantAgentConfig
from app.models.risk_schemas import RiskAgentConfig, LiveComplianceChecklist

logger = logging.getLogger("workflow_graph")


@dataclass
class WorkflowAgents:
    data_ingestion: DataIngestionAgent
    sentiment: SentimentAgent
    quant: QuantAnalyticsAgent
    risk: RiskManagerAgent
    execution: ExecutionAgent
    iv_history: IVHistoryBuffer


def build_graph():
    graph = StateGraph(TradingWorkflowState)

    async def _data_ingestion(state: TradingWorkflowState, config: RunnableConfig) -> TradingWorkflowState:
        agents: WorkflowAgents = config["configurable"]["agents"]
        return await data_ingestion_node(state, agents.data_ingestion)

    async def _sentiment(state: TradingWorkflowState, config: RunnableConfig) -> TradingWorkflowState:
        agents: WorkflowAgents = config["configurable"]["agents"]
        return await sentiment_node(state, agents.sentiment)

    async def _quant(state: TradingWorkflowState, config: RunnableConfig) -> TradingWorkflowState:
        agents: WorkflowAgents = config["configurable"]["agents"]
        return await quant_analytics_node(state, agents.quant, agents.iv_history)

    async def _risk(state: TradingWorkflowState, config: RunnableConfig) -> TradingWorkflowState:
        agents: WorkflowAgents = config["configurable"]["agents"]
        return await risk_manager_node(state, agents.risk)

    async def _execution(state: TradingWorkflowState, config: RunnableConfig) -> TradingWorkflowState:
        agents: WorkflowAgents = config["configurable"]["agents"]
        return await execution_node(state, agents.execution)

    graph.add_node("data_ingestion", _data_ingestion)
    graph.add_node("sentiment", _sentiment)
    graph.add_node("quant_analytics", _quant)
    graph.add_node("risk_manager", _risk)
    graph.add_node("execution", _execution)

    graph.add_edge(START, "data_ingestion")

    def _route_after_data_ingestion(state: TradingWorkflowState) -> str:
        return "end" if state.cycle_status == "halted" else "sentiment"

    graph.add_conditional_edges("data_ingestion", _route_after_data_ingestion, {"sentiment": "sentiment", "end": END})
    graph.add_edge("sentiment", "quant_analytics")
    graph.add_edge("quant_analytics", "risk_manager")

    def _route_after_risk(state: TradingWorkflowState) -> str:
        return "end" if state.cycle_status == "halted" else "execution"

    graph.add_conditional_edges("risk_manager", _route_after_risk, {"execution": "execution", "end": END})
    graph.add_edge("execution", END)

    return graph.compile()


def build_workflow_agents(fyers_client, llm_router, news_client, quant_config, risk_config, risk_free_rate,
                            underlying, performance_tracker=None, live_compliance_checklist=None,
                            algo_id_tag=None, iv_history=None) -> WorkflowAgents:
    data_ingestion = DataIngestionAgent(fyers_client, news_client, risk_free_rate)
    sentiment = SentimentAgent(llm_router)
    quant = QuantAnalyticsAgent(quant_config, llm_router)
    risk = RiskManagerAgent(risk_config, fyers_client)
    execution = ExecutionAgent(fyers_client, risk, live_compliance_checklist, algo_id_tag)

    if quant_config.use_performance_feedback and performance_tracker is not None:
        _wrap_quant_with_performance_feedback(quant, performance_tracker, quant_config)

    return WorkflowAgents(data_ingestion=data_ingestion, sentiment=sentiment, quant=quant, risk=risk,
                            execution=execution, iv_history=iv_history or IVHistoryBuffer(underlying=underlying))


def _wrap_quant_with_performance_feedback(quant: QuantAnalyticsAgent, tracker: PerformanceTracker, config: QuantAgentConfig) -> None:
    original = quant.generate_candidate_signals

    def wrapped(*args, **kwargs):
        signals = original(*args, **kwargs)
        return tracker.rank_candidates(signals, config)

    quant.generate_candidate_signals = wrapped  # type: ignore[method-assign]


def build_shared_agents_for_underlyings(underlyings: list, fyers_client, llm_router, news_client, quant_config,
                                          risk_config, risk_free_rate, performance_tracker=None,
                                          live_compliance_checklist=None, algo_id_tag=None) -> dict:
    risk = RiskManagerAgent(risk_config, fyers_client)
    execution = ExecutionAgent(fyers_client, risk, live_compliance_checklist, algo_id_tag)
    data_ingestion = DataIngestionAgent(fyers_client, news_client, risk_free_rate)
    sentiment = SentimentAgent(llm_router)
    quant = QuantAnalyticsAgent(quant_config, llm_router)

    if quant_config.use_performance_feedback and performance_tracker is not None:
        _wrap_quant_with_performance_feedback(quant, performance_tracker, quant_config)

    return {
        underlying: WorkflowAgents(data_ingestion=data_ingestion, sentiment=sentiment, quant=quant,
                                     risk=risk, execution=execution, iv_history=IVHistoryBuffer(underlying=underlying))
        for underlying in underlyings
    }


def _diff_new_log_entries(prev_count: int, state: TradingWorkflowState) -> list[dict]:
    new_entries = state.reasoning_log[prev_count:]
    return [e.model_dump(mode="json") for e in new_entries]


async def run_cycle(compiled_graph, agents: WorkflowAgents, initial_state: TradingWorkflowState, broadcaster=None) -> TradingWorkflowState:
    config = {"configurable": {"agents": agents}}

    if broadcaster is None:
        result_dict = await compiled_graph.ainvoke(initial_state, config=config)
        return TradingWorkflowState(**result_dict)

    underlying = initial_state.underlying
    last_log_count = 0
    final_state_dict: Optional[dict] = None

    await broadcaster.publish(underlying, {"type": "cycle_started", "cycle_id": initial_state.cycle_id,
                                              "trading_mode": initial_state.trading_mode.value})

    async for state_dict in compiled_graph.astream(initial_state, config=config, stream_mode="values"):
        final_state_dict = state_dict
        current_state = TradingWorkflowState(**state_dict)

        new_entries = _diff_new_log_entries(last_log_count, current_state)
        last_log_count = len(current_state.reasoning_log)
        for entry in new_entries:
            await broadcaster.publish(underlying, {"type": "log", "data": entry})

        if current_state.option_chain_snapshot is not None:
            snap = current_state.option_chain_snapshot
            atm = snap.atm_strike or snap.spot.ltp
            calls_by_strike = {c.strike: c for c in snap.calls}
            puts_by_strike = {p.strike: p for p in snap.puts}
            all_strikes = sorted(set(calls_by_strike) | set(puts_by_strike), key=lambda s: abs(s - atm))[:21]
            all_strikes.sort()

            rows = []
            for strike in all_strikes:
                c = calls_by_strike.get(strike)
                p = puts_by_strike.get(strike)
                rows.append({
                    "strike": strike,
                    "call": ({"ltp": c.ltp, "oi": c.open_interest, "iv": round(c.greeks.implied_volatility, 4),
                               "delta": round(c.greeks.delta, 4), "volume": c.volume} if c else None),
                    "put": ({"ltp": p.ltp, "oi": p.open_interest, "iv": round(p.greeks.implied_volatility, 4),
                              "delta": round(p.greeks.delta, 4), "volume": p.volume} if p else None),
                })

            await broadcaster.publish(underlying, {"type": "option_chain", "data": {
                "spot": snap.spot.ltp, "india_vix": snap.spot.india_vix, "atm_strike": snap.atm_strike,
                "expiry": snap.expiry.isoformat(), "num_calls": len(snap.calls), "num_puts": len(snap.puts),
                "put_call_ratio_oi": snap.put_call_ratio_oi, "rows": rows,
            }})

        if current_state.sentiment is not None:
            s = current_state.sentiment
            await broadcaster.publish(underlying, {"type": "sentiment", "data": {
                "sentiment_score": s.sentiment_score, "market_regime": s.market_regime.value,
                "rationale": s.rationale, "llm_provider_used": s.llm_provider_used,
            }})

        if current_state.candidate_signals:
            await broadcaster.publish(underlying, {"type": "signals", "data": [
                {"signal_id": sig.signal_id, "strategy_type": sig.strategy_type.value,
                 "risk_category": sig.risk_category.value, "net_premium": sig.net_premium,
                 "max_loss_estimate": sig.max_loss_estimate, "max_profit_estimate": sig.max_profit_estimate,
                 "confidence_score": sig.confidence_score, "performance_note": sig.performance_note,
                 "rationale": sig.rationale}
                for sig in current_state.candidate_signals
            ]})

        if current_state.orders_created:
            await broadcaster.publish(underlying, {"type": "orders", "data": [
                {"order_id": o.order_id, "status": o.status, "symbol": o.symbol,
                 "quantity": o.quantity, "error_message": o.error_message}
                for o in current_state.orders_created
            ]})

    await broadcaster.publish(underlying, {"type": "cycle_finished", "cycle_id": initial_state.cycle_id,
                                              "cycle_status": final_state_dict.get("cycle_status") if final_state_dict else "errored"})

    return TradingWorkflowState(**final_state_dict) if final_state_dict else initial_state
