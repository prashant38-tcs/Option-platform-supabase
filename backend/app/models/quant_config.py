from __future__ import annotations
from pydantic import BaseModel


class QuantAgentConfig(BaseModel):
    defined_risk_bias: bool = True
    generate_naked_strategies: bool = True

    iv_rank_high_threshold: float = 60.0
    iv_rank_low_threshold: float = 30.0
    bullish_sentiment_threshold: float = 0.25
    bearish_sentiment_threshold: float = -0.25

    otm_wing_width_pct: float = 1.0
    condor_short_strike_delta_target: float = 0.20

    max_bid_ask_spread_pct: float = 5.0
    min_open_interest: int = 1000

    min_days_to_expiry: int = 1
    max_days_to_expiry: int = 45

    use_performance_feedback: bool = True
    min_sample_size_for_feedback: int = 10
    low_confidence_score_threshold: float = 0.0
