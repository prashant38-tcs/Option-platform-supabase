from __future__ import annotations
import logging
from typing import Optional

from app.core.llm_router import LLMRouter, LLMAllProvidersFailedError
from app.core.volatility_analytics import IVHistoryBuffer, compute_volatility_analytics
from app.core.market_calendar import now_ist_naive
from app.models.enums import MarketRegime, RiskCategory
from app.models.market_schemas import OptionChainSnapshot, SentimentSignal, VolatilityAnalytics
from app.models.quant_config import QuantAgentConfig
from app.models.strategy_schemas import TradeSignal
from app.models.agent_state import TradingWorkflowState
from app.agents import strategy_builder as sb

logger = logging.getLogger("quant_analytics_agent")
AGENT_NAME = "QuantAnalyticsAgent"


class QuantAnalyticsAgent:
    def __init__(self, config: QuantAgentConfig, llm_router: Optional[LLMRouter] = None):
        self._config = config
        self._llm = llm_router

    def classify_regime(self, vol: VolatilityAnalytics, sentiment: Optional[SentimentSignal]) -> MarketRegime:
        sentiment_score = sentiment.sentiment_score if sentiment else 0.0
        if vol.iv_rank >= self._config.iv_rank_high_threshold:
            return MarketRegime.HIGH_VOLATILITY
        if vol.iv_rank <= self._config.iv_rank_low_threshold and vol.iv_rank > 0:
            return MarketRegime.LOW_VOLATILITY
        if sentiment_score >= self._config.bullish_sentiment_threshold:
            return MarketRegime.BULLISH
        if sentiment_score <= self._config.bearish_sentiment_threshold:
            return MarketRegime.BEARISH
        return MarketRegime.NEUTRAL_RANGE_BOUND

    def _passes_liquidity_gate(self, signal: TradeSignal, snapshot: OptionChainSnapshot) -> bool:
        for leg in signal.legs:
            pool = snapshot.calls if leg.option_type.value == "CE" else snapshot.puts
            item = next((i for i in pool if abs(i.strike - leg.strike) < 1e-6), None)
            if item is None:
                return False
            if item.open_interest < self._config.min_open_interest:
                return False
            spread_pct = item.bid_ask_spread_pct
            if spread_pct is not None and spread_pct > self._config.max_bid_ask_spread_pct:
                return False
        return True

    def _select_strikes(self, snapshot: OptionChainSnapshot) -> dict:
        spot = snapshot.spot.ltp
        atm = snapshot.atm_strike
        wing = spot * (self._config.otm_wing_width_pct / 100.0)

        def nearest(pool, target):
            item = min(pool, key=lambda i: abs(i.strike - target), default=None)
            return item.strike if item else None

        return {"atm": atm, "call_otm_near": nearest(snapshot.calls, atm + wing),
                "call_otm_far": nearest(snapshot.calls, atm + 2 * wing),
                "put_otm_near": nearest(snapshot.puts, atm - wing),
                "put_otm_far": nearest(snapshot.puts, atm - 2 * wing)}

    def generate_candidate_signals(self, snapshot: OptionChainSnapshot, vol: VolatilityAnalytics,
                                     sentiment: Optional[SentimentSignal] = None, lots: int = 1) -> list[TradeSignal]:
        regime = self.classify_regime(vol, sentiment)
        strikes = self._select_strikes(snapshot)
        defined_builders: list[TradeSignal] = []
        naked_builders: list[TradeSignal] = []

        if regime == MarketRegime.BULLISH and strikes["atm"] and strikes["call_otm_far"]:
            sig = sb.build_bull_call_spread(snapshot, strikes["atm"], strikes["call_otm_far"], lots)
            if sig:
                defined_builders.append(sig)

        if regime == MarketRegime.BEARISH and strikes["atm"] and strikes["put_otm_far"]:
            sig = sb.build_bear_put_spread(snapshot, strikes["atm"], strikes["put_otm_far"], lots)
            if sig:
                defined_builders.append(sig)

        if regime in (MarketRegime.NEUTRAL_RANGE_BOUND, MarketRegime.HIGH_VOLATILITY):
            if all([strikes["put_otm_far"], strikes["put_otm_near"], strikes["call_otm_near"], strikes["call_otm_far"]]):
                sig = sb.build_iron_condor(snapshot, strikes["put_otm_far"], strikes["put_otm_near"],
                                            strikes["call_otm_near"], strikes["call_otm_far"], lots)
                if sig:
                    defined_builders.append(sig)

        if regime == MarketRegime.LOW_VOLATILITY and strikes["atm"]:
            sig = sb.build_long_straddle(snapshot, strikes["atm"], lots)
            if sig:
                defined_builders.append(sig)

        if self._config.generate_naked_strategies:
            if regime in (MarketRegime.NEUTRAL_RANGE_BOUND, MarketRegime.HIGH_VOLATILITY) and strikes["atm"]:
                sig = sb.build_short_straddle(snapshot, strikes["atm"], lots)
                if sig:
                    naked_builders.append(sig)
                if strikes["put_otm_near"] and strikes["call_otm_near"]:
                    sig2 = sb.build_short_strangle(snapshot, strikes["put_otm_near"], strikes["call_otm_near"], lots)
                    if sig2:
                        naked_builders.append(sig2)

        defined_builders = [s for s in defined_builders if self._passes_liquidity_gate(s, snapshot)]
        naked_builders = [s for s in naked_builders if self._passes_liquidity_gate(s, snapshot)]

        candidates = defined_builders + naked_builders if self._config.defined_risk_bias else naked_builders + defined_builders

        for sig in candidates:
            sig.sentiment_context = (f"Regime={regime.value}, IV_rank={vol.iv_rank:.1f}, "
                                       f"sentiment={sentiment.sentiment_score if sentiment else 'n/a'}")
        return candidates

    async def enrich_rationale_with_llm(self, signal: TradeSignal, regime: MarketRegime) -> TradeSignal:
        if self._llm is None:
            return signal
        try:
            prompt = (f"In 2-3 plain sentences, explain why a {signal.strategy_type.value} strategy on "
                      f"{signal.underlying.value} makes sense given market regime '{regime.value}'. "
                      f"Strikes/legs are already fixed -- just explain the reasoning in trader-friendly language. "
                      f"Do not suggest different strikes.")
            resp = await self._llm.chat(
                system_prompt="You are a concise options trading analyst explaining a strategy already selected by a deterministic quant engine. Never contradict the given strategy or strikes.",
                user_prompt=prompt, temperature=0.3, max_tokens=200,
            )
            signal.rationale = f"{signal.rationale} | {resp.content.strip()}"
        except LLMAllProvidersFailedError as exc:
            logger.warning("LLM narrative enrichment failed for %s: %s (keeping deterministic rationale)", signal.signal_id, exc)
        return signal


async def quant_analytics_node(state: TradingWorkflowState, agent: QuantAnalyticsAgent, iv_history: IVHistoryBuffer) -> TradingWorkflowState:
    if state.option_chain_snapshot is None:
        state.log(AGENT_NAME, "No option chain snapshot available -- skipping quant analysis", level="warning")
        return state

    now = now_ist_naive()
    vol = compute_volatility_analytics(state.option_chain_snapshot, iv_history, now)
    state.volatility_analytics = vol
    iv_history.add_observation(vol.atm_iv)

    regime = agent.classify_regime(vol, state.sentiment)
    signals = agent.generate_candidate_signals(state.option_chain_snapshot, vol, state.sentiment)

    for sig in signals:
        await agent.enrich_rationale_with_llm(sig, regime)

    state.candidate_signals = signals
    defined_count = sum(1 for s in signals if s.risk_category == RiskCategory.DEFINED_RISK)
    naked_count = sum(1 for s in signals if s.risk_category == RiskCategory.UNDEFINED_RISK)
    state.log(AGENT_NAME, f"Regime={regime.value} | Generated {len(signals)} candidates "
              f"({defined_count} defined-risk, {naked_count} undefined-risk/naked)", level="info")
    return state
