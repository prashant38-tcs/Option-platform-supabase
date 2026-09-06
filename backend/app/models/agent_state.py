from __future__ import annotations
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field

from .enums import Underlying, TradingMode, LLMProvider
from .market_schemas import OptionChainSnapshot, VolatilityAnalytics, SentimentSignal, NewsHeadline
from .strategy_schemas import TradeSignal, RiskReview, ManagedOrder
from .risk_schemas import DailyRiskState


class AgentLogEntry(BaseModel):
    timestamp: datetime
    agent_name: str
    message: str
    level: Literal["info", "warning", "error", "decision"] = "info"
    llm_provider_used: Optional[LLMProvider] = None


class TradingWorkflowState(BaseModel):
    cycle_id: str
    underlying: Underlying
    trading_mode: TradingMode
    started_at: datetime
    reasoning_log: list[AgentLogEntry] = Field(default_factory=list)

    option_chain_snapshot: Optional[OptionChainSnapshot] = None
    recent_headlines: list[NewsHeadline] = Field(default_factory=list)
    data_ingestion_errors: list[str] = Field(default_factory=list)

    volatility_analytics: Optional[VolatilityAnalytics] = None
    candidate_signals: list[TradeSignal] = Field(default_factory=list)

    sentiment: Optional[SentimentSignal] = None

    daily_risk_state: Optional[DailyRiskState] = None
    risk_reviews: list[RiskReview] = Field(default_factory=list)
    approved_signals: list[TradeSignal] = Field(default_factory=list)

    orders_created: list[ManagedOrder] = Field(default_factory=list)

    completed_at: Optional[datetime] = None
    cycle_status: Literal["running", "completed", "halted", "errored"] = "running"
    halt_or_error_reason: Optional[str] = None

    def log(self, agent_name: str, message: str, level: str = "info",
             provider: Optional[LLMProvider] = None) -> None:
        self.reasoning_log.append(
            AgentLogEntry(
                timestamp=datetime.utcnow(),
                agent_name=agent_name,
                message=message,
                level=level,  # type: ignore[arg-type]
                llm_provider_used=provider,
            )
        )
