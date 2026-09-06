from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime

from scipy.stats import norm

_MIN_IV = 1e-4
_MAX_IV = 5.0
_MAX_ITER = 100
_TOLERANCE = 1e-6


@dataclass
class BSResult:
    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    implied_volatility: float


def _d1_d2(spot: float, strike: float, t: float, r: float, sigma: float) -> tuple[float, float]:
    if t <= 0 or sigma <= 0:
        raise ValueError("time_to_expiry and sigma must be > 0")
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    return d1, d2


def bs_price(spot: float, strike: float, t: float, r: float, sigma: float, is_call: bool) -> float:
    if t <= 0:
        return max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
    d1, d2 = _d1_d2(spot, strike, t, r, sigma)
    if is_call:
        return spot * norm.cdf(d1) - strike * math.exp(-r * t) * norm.cdf(d2)
    return strike * math.exp(-r * t) * norm.cdf(-d2) - spot * norm.cdf(-d1)


def bs_greeks(spot: float, strike: float, t: float, r: float, sigma: float, is_call: bool) -> BSResult:
    if t <= 0:
        intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
        return BSResult(price=intrinsic, delta=(1.0 if is_call else -1.0) if spot != strike else 0.5,
                         gamma=0.0, theta=0.0, vega=0.0, rho=0.0, implied_volatility=sigma)

    d1, d2 = _d1_d2(spot, strike, t, r, sigma)
    pdf_d1 = norm.pdf(d1)
    price = bs_price(spot, strike, t, r, sigma, is_call)
    delta = norm.cdf(d1) if is_call else norm.cdf(d1) - 1.0
    gamma = pdf_d1 / (spot * sigma * math.sqrt(t))
    vega = spot * pdf_d1 * math.sqrt(t) * 0.01

    if is_call:
        theta_annual = (
            -(spot * pdf_d1 * sigma) / (2 * math.sqrt(t))
            - r * strike * math.exp(-r * t) * norm.cdf(d2)
        )
        rho = strike * t * math.exp(-r * t) * norm.cdf(d2) * 0.01
    else:
        theta_annual = (
            -(spot * pdf_d1 * sigma) / (2 * math.sqrt(t))
            + r * strike * math.exp(-r * t) * norm.cdf(-d2)
        )
        rho = -strike * t * math.exp(-r * t) * norm.cdf(-d2) * 0.01

    theta_per_day = theta_annual / 365.0
    return BSResult(price=price, delta=delta, gamma=gamma, theta=theta_per_day,
                     vega=vega, rho=rho, implied_volatility=sigma)


def implied_volatility(
    market_price: float, spot: float, strike: float, t: float, r: float, is_call: bool,
    initial_guess: float = 0.25,
) -> float:
    if market_price <= 0 or t <= 0:
        raise ValueError("market_price and t must be > 0 to solve for IV")

    sigma = initial_guess
    for _ in range(_MAX_ITER):
        try:
            d1, _ = _d1_d2(spot, strike, t, r, sigma)
        except ValueError:
            break
        price = bs_price(spot, strike, t, r, sigma, is_call)
        vega_raw = spot * norm.pdf(d1) * math.sqrt(t)
        diff = price - market_price
        if abs(diff) < _TOLERANCE:
            return max(min(sigma, _MAX_IV), _MIN_IV)
        if vega_raw < 1e-8:
            break
        sigma -= diff / vega_raw
        if sigma <= 0:
            sigma = _MIN_IV
        if sigma > _MAX_IV:
            sigma = _MAX_IV

    lo, hi = _MIN_IV, _MAX_IV
    for _ in range(200):
        mid = (lo + hi) / 2
        price = bs_price(spot, strike, t, r, mid, is_call)
        if abs(price - market_price) < _TOLERANCE:
            return mid
        if price > market_price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def time_to_expiry_years(now: datetime, expiry: datetime) -> float:
    delta_seconds = (expiry - now).total_seconds()
    return max(delta_seconds, 0.0) / (365.0 * 24 * 3600)


def compute_full_greeks(
    market_price: float, spot: float, strike: float, now: datetime, expiry: datetime,
    r: float, is_call: bool,
) -> BSResult:
    t = time_to_expiry_years(now, expiry)
    if t <= 0:
        intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
        return BSResult(price=intrinsic, delta=(1.0 if (is_call and spot > strike) else (-1.0 if not is_call and spot < strike else 0.0)),
                         gamma=0.0, theta=0.0, vega=0.0, rho=0.0, implied_volatility=0.0)
    sigma = implied_volatility(market_price, spot, strike, t, r, is_call)
    return bs_greeks(spot, strike, t, r, sigma, is_call)


def to_computed_greeks(result: BSResult, r: float, t: float):
    from datetime import timezone
    from app.models.market_schemas import ComputedGreeks
    return ComputedGreeks(
        delta=result.delta, gamma=result.gamma, theta=result.theta,
        vega=result.vega, rho=result.rho, implied_volatility=result.implied_volatility,
        computed_at=datetime.now(timezone.utc), risk_free_rate_used=r, time_to_expiry_years=t,
    )
