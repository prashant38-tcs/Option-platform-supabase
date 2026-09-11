"""
In-memory store for currently OPEN positions (Paper and Live), keyed by a
generated position_id. This complements RiskManagerAgent's aggregate
counters (open_positions_count / current_portfolio_delta / vega) with the
actual per-position detail needed to:
  1. Show a real "Open Positions" view (previously missing entirely --
     the Risk Manager only ever tracked COUNTS, never the underlying
     position records themselves).
  2. Automatically close positions at expiry, crediting/debiting the
     realized P&L back into RiskManagerAgent's daily state and freeing up
     the position slot for new signals -- previously ALSO missing: the
     live/paper cycle had no expiry-based closing logic at all (only the
     separate backtest engine did), which is why positions opened during
     testing never closed and silently filled up the 3-position cap.

Intentionally a simple in-memory list (consistent with the rest of this
app's current state management). Resets on every backend restart/redeploy.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.models.enums import Underlying, TradingMode, FyersOrderSide, OptionType
from app.models.strategy_schemas import TradeSignal


@dataclass
class OpenPosition:
    position_id: str
    underlying: Underlying
    trading_mode: TradingMode
    signal: TradeSignal
    opened_at: datetime


class PositionStore:
    def __init__(self):
        self._positions: dict[str, OpenPosition] = {}

    def add(self, position: OpenPosition) -> None:
        self._positions[position.position_id] = position

    def remove(self, position_id: str) -> Optionalreturn self._positions.pop(position_id, None)

    def all(self) -> listreturn list(self._positions.values())

    def for_underlying(self, underlying: Underlying) -> listreturn [p for p in self._positions.values() if p.underlying == underlying]

    def count(self) -> int:
        return len(self._positions)


def compute_leg_payoff_at_spot(leg, spot: float) -> float:
    """Intrinsic value of one leg at a given spot price -- used to mark a
    position to its EXPIRY value (European index options settle at
    intrinsic value, no time value left)."""
    is_call = leg.option_type == OptionType.CE
    intrinsic = max(spot - leg.strike, 0.0) if is_call else max(leg.strike - spot, 0.0)
    sign = 1 if leg.side == FyersOrderSide.BUY else -1
    return (intrinsic - leg.entry_price_hint) * leg.total_quantity * sign


def compute_position_realized_pnl(signal: TradeSignal, spot: float) -> float:
    return sum(compute_leg_payoff_at_spot(leg, spot) for leg in signal.legs)


def is_position_expired(signal: TradeSignal, now: datetime) -> bool:
    """A multi-leg position's legs all share the same expiry (enforced at
    signal-construction time), so checking the first leg is sufficient."""
    if not signal.legs:
        return False
    return now.date() >= signal.legs[0].expiry.date()
