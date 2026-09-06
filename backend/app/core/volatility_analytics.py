from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from app.models.enums import Underlying, OptionType
from app.models.market_schemas import OptionChainSnapshot, IVSurfacePoint, VolatilityAnalytics

_DEFAULT_LOOKBACK = 252
_MIN_SAMPLES_FOR_RANK = 20


@dataclass
class IVHistoryBuffer:
    underlying: Underlying
    lookback: int = _DEFAULT_LOOKBACK
    _values: deque = field(default_factory=lambda: deque(maxlen=_DEFAULT_LOOKBACK))

    def __post_init__(self):
        self._values = deque(maxlen=self.lookback)

    def add_observation(self, atm_iv: float) -> None:
        self._values.append(atm_iv)

    def sample_count(self) -> int:
        return len(self._values)

    def values(self) -> list[float]:
        return list(self._values)


def build_iv_surface(snapshot: OptionChainSnapshot) -> list[IVSurfacePoint]:
    points: list[IVSurfacePoint] = []
    spot = snapshot.spot.ltp
    for item in snapshot.calls:
        points.append(IVSurfacePoint(strike=item.strike, option_type=OptionType.CE,
                                       implied_volatility=item.greeks.implied_volatility,
                                       moneyness=round(item.strike / spot, 4) if spot else 0.0))
    for item in snapshot.puts:
        points.append(IVSurfacePoint(strike=item.strike, option_type=OptionType.PE,
                                       implied_volatility=item.greeks.implied_volatility,
                                       moneyness=round(item.strike / spot, 4) if spot else 0.0))
    return points


def compute_atm_iv(snapshot: OptionChainSnapshot) -> float:
    atm = snapshot.atm_strike
    if atm is None:
        raise ValueError("Cannot compute ATM IV: no strikes in snapshot")
    call_iv = next((c.greeks.implied_volatility for c in snapshot.calls if c.strike == atm), None)
    put_iv = next((p.greeks.implied_volatility for p in snapshot.puts if p.strike == atm), None)
    ivs = [iv for iv in (call_iv, put_iv) if iv is not None]
    if not ivs:
        raise ValueError(f"No IV data found at ATM strike {atm}")
    return sum(ivs) / len(ivs)


def compute_skew(snapshot: OptionChainSnapshot, otm_distance_pct: float = 0.03) -> float:
    spot = snapshot.spot.ltp
    if not spot:
        return 0.0
    target_put_strike = spot * (1 - otm_distance_pct)
    target_call_strike = spot * (1 + otm_distance_pct)
    nearest_put = min(snapshot.puts, key=lambda p: abs(p.strike - target_put_strike), default=None)
    nearest_call = min(snapshot.calls, key=lambda c: abs(c.strike - target_call_strike), default=None)
    if not nearest_put or not nearest_call:
        return 0.0
    return round(nearest_put.greeks.implied_volatility - nearest_call.greeks.implied_volatility, 5)


def compute_iv_rank_percentile(current_atm_iv: float, history: IVHistoryBuffer) -> tuple[float, float, bool]:
    values = history.values()
    if len(values) < _MIN_SAMPLES_FOR_RANK:
        return 0.0, 0.0, True
    v_min, v_max = min(values), max(values)
    iv_rank = 0.0 if v_max == v_min else ((current_atm_iv - v_min) / (v_max - v_min)) * 100.0
    iv_rank = max(0.0, min(100.0, iv_rank))
    below_count = sum(1 for v in values if v <= current_atm_iv)
    iv_percentile = (below_count / len(values)) * 100.0
    return round(iv_rank, 2), round(iv_percentile, 2), False


def compute_volatility_analytics(snapshot: OptionChainSnapshot, history: IVHistoryBuffer, now: datetime) -> VolatilityAnalytics:
    atm_iv = compute_atm_iv(snapshot)
    iv_rank, iv_percentile, insufficient = compute_iv_rank_percentile(atm_iv, history)
    skew = compute_skew(snapshot)
    surface = build_iv_surface(snapshot)
    return VolatilityAnalytics(underlying=snapshot.underlying, expiry=snapshot.expiry,
                                 iv_rank=iv_rank, iv_percentile=iv_percentile, atm_iv=atm_iv,
                                 skew=skew, iv_surface=surface, computed_at=now)
