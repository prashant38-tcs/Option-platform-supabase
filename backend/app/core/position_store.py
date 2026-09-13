from __future__ import annotations 
from dataclasses import dataclass 
from datetime import datetime 

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
            self._positions = {} 

        def add(self, position): 
                self._positions[position.position_id] = position 

        def remove(self, position_id): 
            return self._positions.pop(position_id, None) 

        def all(self): 
            return list(self._positions.values()) 

        def for_underlying(self, underlying): 
            matches = [] 
            for p in self._positions.values(): 
                if p.underlying == underlying: 
                    matches.append(p) 
                    return matches 

        def count(self): 
            return len(self._positions) 
            
        def compute_leg_payoff_at_spot(leg, spot): 
            is_call = leg.option_type == OptionType.CE 
            if is_call: intrinsic = max(spot - leg.strike, 0.0) 
            else: intrinsic = max(leg.strike - spot, 0.0) 
            if leg.side == FyersOrderSide.BUY: 
                sign = 1 

            else: sign = -1 

            return (intrinsic - leg.entry_price_hint) * leg.total_quantity * sign 
        def compute_position_realized_pnl(signal, spot): 
            total = 0.0 
            for leg in signal.legs: 
                total = total + compute_leg_payoff_at_spot(leg, spot) 
                return total 
            
        def is_position_expired(signal, now): 
            if not signal.legs: 
                return False 
            if now.date() >= signal.legs[0].expiry.date(): 
                return True 

            return False
