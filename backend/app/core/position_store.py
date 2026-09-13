"""
In-memory store for currently OPEN positions (Paper and Live), keyed by a
generated position_id.
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

    def remove(self, position_id: str) -> Optional[OpenPosition]:
        returnition_id, None)

    def all(self) -> listreturn list(self._positions.values())

    def for_underlying(self, underlying: Underlying) -> list[OpenPosition]:
        return [p .values() if p.underlying == underlying]

    def count(self) -> int:
        return len(self._positions)


def compute_leg_payoff_at_spot(leg, spot: float) -> float:
    is_call = leg.option_type == OptionType.CE
    intrinsic = max(spot - leg.strike, 0.0) if is_call else max(leg.strike - spot, 0.0)
    sign = 1 if leg.side == FyersOrderSide.BUY else -1
    return (intrinsic - leg.entry_price_hint) * leg.total_quantity * sign


def compute_position_realized_pnl(signal: TradeSignal, spot: float) -> float:
    return sum(compute_leg_payoff_at_spot(leg, spot) for leg in signal.legs)


def is_position_expired(signal: TradeSignal, now: datetime) -> bool:
    if not signal.legs:
        return False
    return now.date() >= signal.legs[0].expiry.date()
