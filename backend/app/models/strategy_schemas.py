from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, computed_field, ConfigDict

from .enums import (
    Underlying, OptionType, StrategyType, TradingMode,
    OrderLifecycleStatus, FyersOrderSide, FyersProductType, RiskCategory,
)
from .market_schemas import ComputedGreeks


class StrategyLeg(BaseModel):
    underlying: Underlying
    expiry: datetime
    strike: float
    option_type: OptionType
    side: FyersOrderSide
    lots: int = Field(gt=0)
    lot_size: int = Field(gt=0)
    symbol: str
    entry_price_hint: float
    greeks_at_signal: ComputedGreeks

    @computed_field
    @property
    def total_quantity(self) -> int:
        return self.lots * self.lot_size


class TradeSignal(BaseModel):
    signal_id: str
    generated_at: datetime
    underlying: Underlying
    strategy_type: StrategyType
    risk_category: RiskCategory
    legs: list[StrategyLeg]
    rationale: str
    sentiment_context: Optional[str] = None
    max_loss_estimate: Optional[float] = None
    max_profit_estimate: Optional[float] = None
    breakeven_points: list[float] = Field(default_factory=list)
    net_premium: float

    confidence_score: Optional[float] = None
    historical_win_rate: Optional[float] = None
    historical_sample_size: int = 0
    performance_note: Optional[str] = None

    @computed_field
    @property
    def net_delta(self) -> float:
        total = 0.0
        for leg in self.legs:
            sign = 1 if leg.side == FyersOrderSide.BUY else -1
            total += sign * leg.greeks_at_signal.delta * leg.total_quantity
        return round(total, 2)

    @computed_field
    @property
    def net_vega(self) -> float:
        total = 0.0
        for leg in self.legs:
            sign = 1 if leg.side == FyersOrderSide.BUY else -1
            total += sign * leg.greeks_at_signal.vega * leg.total_quantity
        return round(total, 2)


class RiskReview(BaseModel):
    signal_id: str
    reviewed_at: datetime
    approved: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    capital_at_risk: float
    capital_at_risk_pct_of_equity: float
    projected_portfolio_delta_after: float
    projected_portfolio_vega_after: float
    daily_pnl_at_review_time: float
    daily_loss_circuit_breaker_tripped: bool
    daily_profit_target_reached: bool
    is_zero_or_near_dte: bool
    notes: str = ""


class ManagedOrder(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    order_id: str
    signal_id: str
    trading_mode: TradingMode
    status: OrderLifecycleStatus
    created_at: datetime
    updated_at: datetime
    symbol: str
    side: Optional[FyersOrderSide] = None
    product_type: FyersProductType
    quantity: int
    limit_price: float
    filled_price: Optional[float] = None
    broker_order_id: Optional[str] = None
    order_tag_algo_id: Optional[str] = None
    error_message: Optional[str] = None


class Position(BaseModel):
    position_id: str
    trading_mode: TradingMode
    underlying: Underlying
    legs: list[StrategyLeg]
    opened_at: datetime
    entry_net_premium: float
    current_net_premium: float
    unrealized_pnl: float
    current_portfolio_delta: float
    current_portfolio_vega: float
    stop_loss_level: Optional[float] = None
    take_profit_level: Optional[float] = None
