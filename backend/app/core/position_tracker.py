from __future__ import annotations
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

from app.models.strategy_schemas import TradeSignal
from app.models.enums import TradingMode


@dataclass
class OpenPosition:
    position_id: str
    signal: TradeSignal
    trading_mode: TradingMode
    opened_at: datetime
    entry_net_premium: float
    current_pnl: float = 0.0

    @property
    def strategy_type(self) -> str:
        return self.signal.strategy_type.value

    @property
    def underlying(self) -> str:
        return self.signal.underlying.value

    @property
    def expiry(self) -> datetime:
        return self.signal.legs[0].expiry if self.signal.legs else self.opened_at

    @property
    def days_to_expiry(self) -> int:
        delta = self.expiry - datetime.now()
        return max(delta.days, 0)

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "underlying": self.underlying,
            "strategy_type": self.strategy_type,
            "trading_mode": self.trading_mode.value,
            "opened_at": self.opened_at.isoformat(),
            "entry_net_premium": self.entry_net_premium,
            "current_pnl": self.current_pnl,
            "expiry": self.expiry.isoformat(),
            "days_to_expiry": self.days_to_expiry,
            "legs": [
                {"strike": leg.strike, "option_type": leg.option_type.value, "side": leg.side.value if hasattr(leg.side, "value") else leg.side}
                for leg in self.signal.legs
            ],
        }


class PositionTracker:
    """In-memory registry of currently open Paper/Live positions, keyed
    by underlying. This does NOT replace the RiskManagerAgent's own
    exposure counters (open_positions_count/delta/vega) -- it exists
    purely so the dashboard/API has something human-readable to show,
    since the Risk Manager only tracks aggregate numbers, not which
    specific positions are open."""

    def __init__(self):
        self._positions: dict[str, list[OpenPosition]] = {}

    def add_position(self, underlying: str, signal: TradeSignal, trading_mode: TradingMode, now: datetime) -> OpenPosition:
        pos = OpenPosition(
            position_id=f"pos-{signal.signal_id}",
            signal=signal,
            trading_mode=trading_mode,
            opened_at=now,
            entry_net_premium=signal.net_premium,
        )
        self._positions.setdefault(underlying, []).append(pos)
        return pos

    def get_open_positions(self, underlying: str) -> list[OpenPosition]:
        return list(rlying, []))

    def remove_position(self, underlying: str, position_id: str) -> None:
        if underlying in self._positions:
            self._positions[underlying] = [p for p in self._positions[underlying] if p.position_id != position_id]

    def count(self, underlying: str) -> int:
        return len(self._positions.get(underlying, []))
