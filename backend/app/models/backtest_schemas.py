from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, computed_field

from .enums import Underlying, StrategyType, RiskCategory


class DataSourceQuality(BaseModel):
    source: str
    underlying_price_source: str
    volatility_proxy_used: Optional[str] = None
    coverage_start: datetime
    coverage_end: datetime
    caveats: list[str] = Field(default_factory=list)


class BacktestTrade(BaseModel):
    trade_id: str
    underlying: Underlying
    strategy_type: StrategyType
    risk_category: RiskCategory
    entry_date: datetime
    exit_date: datetime
    entry_net_premium: float
    exit_net_premium: float
    capital_deployed: float
    realized_pnl: float
    exit_reason: str
    max_loss_estimate_at_entry: Optional[float] = None
    max_profit_estimate_at_entry: Optional[float] = None

    @computed_field
    @property
    def return_pct_on_capital(self) -> float:
        if self.capital_deployed == 0:
            return 0.0
        return round((self.realized_pnl / self.capital_deployed) * 100.0, 3)

    @computed_field
    @property
    def is_win(self) -> bool:
        return self.realized_pnl > 0


class EquityCurvePoint(BaseModel):
    date: datetime
    equity: float
    daily_pnl: float
    drawdown_pct: float


class StrategyPerformanceStats(BaseModel):
    strategy_type: StrategyType
    risk_category: RiskCategory
    sample_size: int
    win_rate: float
    avg_pnl_per_trade: float
    avg_return_pct_on_capital: float
    max_drawdown_pct: float
    total_pnl: float
    composite_score: float
    computed_at: datetime
    data_sources_included: list[str] = Field(default_factory=list)


class BacktestReport(BaseModel):
    run_id: str
    underlying: Underlying
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    data_quality: DataSourceQuality
    trades: list[BacktestTrade] = Field(default_factory=list)
    equity_curve: list[EquityCurvePoint] = Field(default_factory=list)
    per_strategy_stats: list[StrategyPerformanceStats] = Field(default_factory=list)
    generated_at: datetime

    @computed_field
    @property
    def total_return_pct(self) -> float:
        if self.initial_capital == 0:
            return 0.0
        return round(((self.final_capital - self.initial_capital) / self.initial_capital) * 100.0, 3)

    @computed_field
    @property
    def overall_win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.is_win)
        return round(wins / len(self.trades), 4)

    @computed_field
    @property
    def max_drawdown_pct(self) -> float:
        if not self.equity_curve:
            return 0.0
        return min((p.drawdown_pct for p in self.equity_curve), default=0.0)
