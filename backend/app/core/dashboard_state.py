from __future__ import annotations
from typing import Optional

from app.models.enums import Underlying, TradingMode


class DashboardState:
    def __init__(self, default_mode: TradingMode = TradingMode.ADVISORY):
        self._mode_by_underlying: dict[Underlying, TradingMode] = {}
        self._default_mode = default_mode
        self._manual_capital_override: Optional[float] = None

    def get_trading_mode(self, underlying: Underlying) -> TradingMode:
        return self._mode_by_underlying.get(underlying, self._default_mode)

    def set_trading_mode(self, underlying: Underlying, mode: TradingMode) -> None:
        self._mode_by_underlying[underlying] = mode

    def set_all_trading_modes(self, mode: TradingMode) -> None:
        self._default_mode = mode
        for u in list(self._mode_by_underlying.keys()):
            self._mode_by_underlying[u] = mode

    def get_capital_override(self) -> Optional[float]:
        return self._manual_capital_override

    def set_capital_override(self, capital: float) -> None:
        if capital <= 0:
            raise ValueError("Capital override must be a positive number")
        self._manual_capital_override = capital
