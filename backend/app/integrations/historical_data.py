from __future__ import annotations
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.integrations.fyers_client import FyersClient, FyersAPIError

logger = logging.getLogger("historical_data")


@dataclass
class HistoricalBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


class HistoricalDataError(RuntimeError):
    pass


async def fetch_underlying_history(client: FyersClient, symbol: str, start: datetime, end: datetime, resolution: str = "D") -> list[HistoricalBar]:
    data = await client.get_history(symbol=symbol, resolution=resolution, range_from=start.strftime("%Y-%m-%d"),
                                      range_to=end.strftime("%Y-%m-%d"), date_format="1")
    candles = data.get("candles", [])
    bars = [HistoricalBar(timestamp=datetime.fromtimestamp(c[0]), open=c[1], high=c[2], low=c[3], close=c[4],
                            volume=int(c[5]) if len(c) > 5 else 0) for c in candles]
    bars.sort(key=lambda b: b.timestamp)
    return bars


async def fetch_option_contract_history(client: FyersClient, option_symbol: str, start: datetime, end: datetime, resolution: str = "D") -> Optional[list[HistoricalBar]]:
    try:
        data = await client.get_history(symbol=option_symbol, resolution=resolution, range_from=start.strftime("%Y-%m-%d"),
                                          range_to=end.strftime("%Y-%m-%d"), date_format="1")
    except FyersAPIError as exc:
        logger.info("No real historical data for %s (%s) -- will use synthetic pricing", option_symbol, exc)
        return None
    candles = data.get("candles", [])
    if not candles:
        return None
    bars = [HistoricalBar(timestamp=datetime.fromtimestamp(c[0]), open=c[1], high=c[2], low=c[3], close=c[4],
                            volume=int(c[5]) if len(c) > 5 else 0) for c in candles]
    bars.sort(key=lambda b: b.timestamp)
    return bars


def compute_realized_volatility(bars: list[HistoricalBar], window: int = 20) -> float:
    if len(bars) < window + 1:
        raise HistoricalDataError(f"Need at least {window + 1} bars to compute {window}-day realized volatility, got {len(bars)}")
    closes = [b.close for b in bars[-(window + 1):]]
    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    mean = sum(log_returns) / len(log_returns)
    variance = sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1)
    daily_stdev = math.sqrt(variance)
    return daily_stdev * math.sqrt(252)


def rolling_realized_vol_series(bars: list[HistoricalBar], window: int = 20) -> list[tuple[datetime, float]]:
    results = []
    for i in range(window, len(bars)):
        window_bars = bars[i - window: i + 1]
        vol = compute_realized_volatility(window_bars, window=window)
        results.append((bars[i].timestamp, vol))
    return results
