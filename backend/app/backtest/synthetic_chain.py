from __future__ import annotations
from datetime import datetime

from app.core.black_scholes import bs_greeks, to_computed_greeks, time_to_expiry_years, BSResult
from app.core.strike_conventions import build_strike_ladder
from app.models.enums import Underlying, OptionType
from app.models.market_schemas import OptionChainItem, OptionChainSnapshot, UnderlyingQuote

_PLACEHOLDER_OI = 2_000_000
_PLACEHOLDER_VOLUME = 500_000
_SYNTHETIC_SPREAD_PCT = 0.003


def build_synthetic_snapshot(underlying: Underlying, spot: float, now: datetime, expiry: datetime,
                              realized_vol: float, risk_free_rate: float, prev_close: float) -> OptionChainSnapshot:
    strikes = build_strike_ladder(underlying, spot)
    t = time_to_expiry_years(now, expiry)

    calls: list[OptionChainItem] = []
    puts: list[OptionChainItem] = []

    for strike in strikes:
        for is_call in (True, False):
            bs_result = bs_greeks(spot, strike, t, risk_free_rate, realized_vol, is_call) if t > 0 else None
            if bs_result is None:
                intrinsic = max((spot - strike) if is_call else (strike - spot), 0.0)
                price = max(intrinsic, 0.05)
                bs_result = BSResult(price=price, delta=(1.0 if is_call else -1.0) if spot != strike else 0.5,
                                       gamma=0.0, theta=0.0, vega=0.0, rho=0.0, implied_volatility=realized_vol)
            price = max(bs_result.price, 0.05)
            greeks = to_computed_greeks(bs_result, risk_free_rate, t)
            spread = max(price * _SYNTHETIC_SPREAD_PCT, 0.05)
            item = OptionChainItem(
                underlying=underlying, expiry=expiry, strike=strike,
                option_type=OptionType.CE if is_call else OptionType.PE,
                symbol=f"SYNTH:{underlying.value}{expiry.strftime('%y%m%d')}{int(strike)}{'CE' if is_call else 'PE'}",
                ltp=round(price, 2), bid=round(price - spread / 2, 2), ask=round(price + spread / 2, 2),
                volume=_PLACEHOLDER_VOLUME, open_interest=_PLACEHOLDER_OI, oi_change=0, oi_change_pct=0, greeks=greeks,
            )
            (calls if is_call else puts).append(item)

    spot_quote = UnderlyingQuote(
        underlying=underlying, ltp=spot, prev_close=prev_close,
        change=round(spot - prev_close, 2), change_pct=round(((spot - prev_close) / prev_close) * 100, 3) if prev_close else 0.0,
        timestamp=now, india_vix=round(realized_vol * 100, 2),
    )
    return OptionChainSnapshot(underlying=underlying, expiry=expiry, spot=spot_quote, calls=calls, puts=puts, fetched_at=now)
