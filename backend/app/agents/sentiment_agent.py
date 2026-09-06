from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.llm_router import LLMRouter, LLMAllProvidersFailedError
from app.models.enums import Underlying, MarketRegime
from app.models.market_schemas import NewsHeadline, SentimentSignal
from app.models.agent_state import TradingWorkflowState

logger = logging.getLogger("sentiment_agent")
AGENT_NAME = "SentimentAgent"

_SYSTEM_PROMPT = (
    "You are a financial news sentiment classifier for Indian equity index markets "
    "(NIFTY, BANKNIFTY, FINNIFTY, SENSEX). Given a list of recent news headlines, "
    "respond with ONLY a JSON object (no markdown, no prose) in exactly this shape: "
    '{"sentiment_score": <float between -1.0 and 1.0>, "regime": '
    '"BULLISH"|"BEARISH"|"NEUTRAL_RANGE_BOUND"|"HIGH_VOLATILITY"|"LOW_VOLATILITY", '
    '"rationale": "<one or two sentence explanation>"}. '
    "Base your judgment ONLY on the headlines provided. If headlines are sparse, "
    "ambiguous, or mostly unrelated to markets, return sentiment_score near 0.0 and "
    "regime NEUTRAL_RANGE_BOUND."
)
_MAX_HEADLINES_IN_PROMPT = 15


class SentimentAgent:
    def __init__(self, llm_router: Optional[LLMRouter]):
        self._llm = llm_router

    async def score_headlines(self, headlines: list[NewsHeadline], underlying: Underlying, now: datetime) -> SentimentSignal:
        if self._llm is None or not headlines:
            return self._neutral_fallback(underlying, headlines, now,
                                            reason="No LLM router configured" if self._llm is None else "No headlines available")

        prompt_headlines = headlines[:_MAX_HEADLINES_IN_PROMPT]
        headline_text = "\n".join(f"- {h.headline}: {h.snippet}" for h in prompt_headlines)
        user_prompt = f"Headlines (most recent first), relevant to Indian markets and {underlying.value}:\n\n{headline_text}\n\nRespond with the JSON object only."

        try:
            response = await self._llm.chat(system_prompt=_SYSTEM_PROMPT, user_prompt=user_prompt,
                                               temperature=0.1, max_tokens=300, json_mode=True)
            parsed = LLMRouter.parse_json_response(response)
            score = float(parsed["sentiment_score"])
            score = max(-1.0, min(1.0, score))
            regime_str = str(parsed.get("regime", "NEUTRAL_RANGE_BOUND")).upper()
            try:
                regime = MarketRegime(regime_str)
            except ValueError:
                regime = MarketRegime.NEUTRAL_RANGE_BOUND
            rationale = str(parsed.get("rationale", "")).strip() or "No rationale provided by LLM."

            return SentimentSignal(related_underlying=underlying, sentiment_score=score, market_regime=regime,
                                     rationale=rationale, contributing_headlines=prompt_headlines,
                                     llm_provider_used=response.provider_used.value, generated_at=now)
        except LLMAllProvidersFailedError as exc:
            logger.warning("Sentiment scoring failed (all LLM providers down): %s -- falling back to neutral", exc)
            return self._neutral_fallback(underlying, headlines, now, reason=f"All LLM providers failed: {exc}")
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Sentiment scoring got malformed LLM response: %s -- falling back to neutral", exc)
            return self._neutral_fallback(underlying, headlines, now, reason=f"Malformed LLM response: {exc}")

    @staticmethod
    def _neutral_fallback(underlying: Underlying, headlines: list[NewsHeadline], now: datetime, reason: str) -> SentimentSignal:
        return SentimentSignal(related_underlying=underlying, sentiment_score=0.0, market_regime=MarketRegime.NEUTRAL_RANGE_BOUND,
                                 rationale=f"Neutral fallback -- {reason}", contributing_headlines=headlines[:_MAX_HEADLINES_IN_PROMPT],
                                 llm_provider_used="NONE", generated_at=now)


async def sentiment_node(state: TradingWorkflowState, agent: SentimentAgent) -> TradingWorkflowState:
    now = datetime.now(timezone.utc)
    sentiment = await agent.score_headlines(state.recent_headlines, state.underlying, now)
    state.sentiment = sentiment
    provider_note = f" (via {sentiment.llm_provider_used})" if sentiment.llm_provider_used != "NONE" else " (LLM unavailable, neutral fallback)"
    state.log(AGENT_NAME, f"Sentiment score={sentiment.sentiment_score:+.2f}, regime={sentiment.market_regime.value}"
              f"{provider_note} | {sentiment.rationale}", level="info")
    return state
