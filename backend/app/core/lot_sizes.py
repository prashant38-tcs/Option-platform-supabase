from __future__ import annotations
from datetime import date
from app.models.enums import Underlying

LOT_SIZES_EFFECTIVE_DATE = date(2026, 1, 1)

CURRENT_LOT_SIZES: dict[Underlying, int] = {
    Underlying.NIFTY: 65,
    Underlying.BANKNIFTY: 30,
    Underlying.FINNIFTY: 60,
    Underlying.SENSEX: 20,
}


def get_lot_size(underlying: Underlying) -> int:
    if underlying not in CURRENT_LOT_SIZES:
        raise ValueError(f"No lot size configured for {underlying}.")
    return CURRENT_LOT_SIZES[underlying]
