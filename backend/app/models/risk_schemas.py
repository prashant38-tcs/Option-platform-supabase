from __future__ import annotations
from datetime import datetime, time
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class RiskAgentConfig(BaseModel):
    model_config = ConfigDict(json_encoders={time: lambda t: t.isoformat()})

    account_capital_source: str = "user_entered"
    manual_capital_override: Optional[float] = None

    daily_profit_target_pct: float = 1.0
    daily_max_loss_pct: float = 1.0
    lock_in_profit_on_target_hit: bool = True

    max_margin_per_position_pct: float = 3.0
    naked_strategy_max_margin_per_position_pct: float = 3.0

    max_concurrent_positions: int = 3

    naked_short_margin_pct_of_notional: float = 12.0

    max_portfolio_delta_per_lakh_capital: float = 100.0
    max_portfolio_vega_per_lakh_capital: float = 2500.0

    block_new_entries_on_expiry_day: bool = True
    expiry_day_cutoff_time: time = time(14, 30)
    allow_zero_dte_override: bool = False

    max_bid_ask_spread_pct: float = 5.0


class DailyRiskState(BaseModel):
    trading_date: datetime
    capital_base: float
    daily_profit_target_amount: float
    daily_max_loss_amount: float
    realized_pnl_today: float = 0.0
    unrealized_pnl_today: float = 0.0

    @property
    def total_pnl_today(self) -> float:
        return self.realized_pnl_today + self.unrealized_pnl_today

    @property
    def profit_target_hit(self) -> bool:
        return self.total_pnl_today >= self.daily_profit_target_amount

    @property
    def loss_circuit_breaker_tripped(self) -> bool:
        return self.total_pnl_today <= -abs(self.daily_max_loss_amount)

    open_positions_count: int = 0
    current_portfolio_delta: float = 0.0
    current_portfolio_vega: float = 0.0
    trading_halted: bool = False
    halt_reason: Optional[str] = None


class ComplianceChecklistItem(BaseModel):
    key: str
    label: str
    is_complete: bool = False
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None


class LiveComplianceChecklist(BaseModel):
    static_ip_whitelisted: ComplianceChecklistItem
    compliant_app_activated: ComplianceChecklistItem
    daily_2fa_flow_tested: ComplianceChecklistItem
    order_rate_under_10_per_sec_confirmed: ComplianceChecklistItem
    algo_id_tagging_wired: ComplianceChecklistItem
    manual_arm_toggle_confirmed: ComplianceChecklistItem

    def all_complete(self) -> bool:
        return all(
            item.is_complete
            for item in (
                self.static_ip_whitelisted,
                self.compliant_app_activated,
                self.daily_2fa_flow_tested,
                self.order_rate_under_10_per_sec_confirmed,
                self.algo_id_tagging_wired,
                self.manual_arm_toggle_confirmed,
            )
        )
