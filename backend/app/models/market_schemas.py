from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, computed_field

from .enums import Underlying, OptionType, MarketRegime


class UnderlyingQuote(BaseModel):
    underlying: Underlying
    ltp: float
    prev_close: float
    change: float
    change_pct: float
    timestamp: datetime
    india_vix: Optional[float] = None


class ComputedGreeks(BaseModel):
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    implied_volatility: float
    computed_at: datetime
    model_used: str = "black_scholes_merton"
    risk_free_rate_used: float
    time_to_expiry_years: float


class OptionChainItem(BaseModel):
    underlying: Underlying
    expiry: datetime
    strike: float
    option_type: OptionType
    symbol: str

    ltp: float
    bid: float
    ask: float
    volume: int
    open_interest: int
    oi_change: float
    oi_change_pct: float

    greeks: ComputedGreeks

    @computed_field
    @property
    def mid_price(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return round((self.bid + self.ask) / 2, 2)
        return self.ltp

    @computed_field
    @property
    def bid_ask_spread_pct(self) -> Optional[float]:
        if self.bid > 0 and self.ask > 0 and self.mid_price > 0:
            return round(((self.ask - self.bid) / self.mid_price) * 100, 3)
        return None


class OptionChainSnapshot(BaseModel):
    underlying: Underlying
    expiry: datetime
    spot: UnderlyingQuote
    calls: list[OptionChainItem]
    puts: list[OptionChainItem]
    fetched_at: datetime

    @computed_field
    @property
    def atm_strike(self) -> Optional[float]:
        all_strikes = {c.strike for c in self.calls} | {p.strike for p in self.puts}
        if not all_strikes:
            return None
        return min(all_strikes, key=lambda s: abs(s - self.spot.ltp))

    @computed_field
    @property
    def put_call_ratio_oi(self) -> Optional[float]:
        total_put_oi = sum(p.open_interest for p in self.puts)
        total_call_oi = sum(c.open_interest for c in self.calls)
        if total_call_oi == 0:
            return None
        return round(total_put_oi / total_call_oi, 3)


class IVSurfacePoint(BaseModel):
    strike: float
    option_type: OptionType
    implied_volatility: float
    moneyness: float


class VolatilityAnalytics(BaseModel):
    underlying: Underlying
    expiry: datetime
    iv_rank: float
    iv_percentile: float
    atm_iv: float
    skew: float
    iv_surface: list[IVSurfacePoint]
    computed_at: datetime


class NewsHeadline(BaseModel):
    source: str = "moneycontrol"
    headline: str
    snippet: str
    url: str
    published_at: Optional[datetime] = None


class SentimentSignal(BaseModel):
    related_underlying: Optional[Underlying] = None
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    market_regime: MarketRegime
    rationale: str
    contributing_headlines: list[NewsHeadline]
    llm_provider_used: str
    generated_at: datetime
