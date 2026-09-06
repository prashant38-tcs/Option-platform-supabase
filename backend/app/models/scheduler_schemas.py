from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from .enums import Underlying, TradingMode


class CycleSummary(BaseModel):
    cycle_id: str
    underlying: Underlying
    trading_mode: TradingMode
    started_at: datetime
    completed_at: Optional[datetime] = None
    cycle_status: str
    halt_or_error_reason: Optional[str] = None
    num_candidate_signals: int = 0
    num_approved_signals: int = 0
    num_orders_created: int = 0
    daily_pnl_at_completion: Optional[float] = None


class UnderlyingScheduleStatus(BaseModel):
    underlying: Underlying
    is_running: bool
    is_market_open: bool
    trading_mode: TradingMode
    total_cycles_run: int = 0
    total_errors: int = 0
    last_cycle_at: Optional[datetime] = None
    last_cycle_status: Optional[str] = None
    next_cycle_at: Optional[datetime] = None
    next_market_open_at: Optional[datetime] = None


class SchedulerStatus(BaseModel):
    is_scheduler_running: bool
    interval_seconds: float
    market_hours_only: bool
    underlyings: list[UnderlyingScheduleStatus] = Field(default_factory=list)
