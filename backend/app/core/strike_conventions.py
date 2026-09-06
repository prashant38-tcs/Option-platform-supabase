from __future__ import annotations
from app.models.enums import Underlying

STRIKE_STEP: dict[Underlying, float] = {
    Underlying.NIFTY: 50.0,
    Underlying.BANKNIFTY: 100.0,
    Underlying.FINNIFTY: 50.0,
    Underlying.SENSEX: 100.0,
}


def get_strike_step(underlying: Underlying) -> float:
    if underlying not in STRIKE_STEP:
        raise ValueError(f"No strike step configured for {underlying}")
    return STRIKE_STEP[underlying]


def build_strike_ladder(underlying: Underlying, spot: float, num_strikes_each_side: int = 15) -> list[float]:
    step = get_strike_step(underlying)
    atm = round(spot / step) * step
    return [atm + i * step for i in range(-num_strikes_each_side, num_strikes_each_side + 1)]
