from __future__ import annotations
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

MARKET_OPEN_TIME = time(9, 15)
MARKET_CLOSE_TIME = time(15, 30)


def now_ist() -> datetime:
    return datetime.now(timezone.utc).astimezone(IST)


def now_ist_naive() -> datetime:
    return now_ist().replace(tzinfo=None)


NSE_TRADING_HOLIDAYS_2026: set[date] = {
    date(2026, 1, 26), date(2026, 3, 3), date(2026, 3, 26), date(2026, 3, 31),
    date(2026, 4, 3), date(2026, 4, 14), date(2026, 5, 1), date(2026, 5, 28),
    date(2026, 6, 26), date(2026, 9, 14), date(2026, 10, 2), date(2026, 10, 20),
    date(2026, 11, 10), date(2026, 11, 24), date(2026, 12, 25),
}

_SUPPORTED_YEARS = {2026}


class UnsupportedCalendarYearError(RuntimeError):
    pass


def _ensure_year_supported(d: date) -> None:
    if d.year not in _SUPPORTED_YEARS:
        raise UnsupportedCalendarYearError(
            f"NSE trading holiday calendar for {d.year} is not configured "
            f"(only {sorted(_SUPPORTED_YEARS)} supported)."
        )


def is_trading_day(d: date) -> bool:
    _ensure_year_supported(d)
    if d.weekday() >= 5:
        return False
    return d not in NSE_TRADING_HOLIDAYS_2026


def _to_ist(now: datetime) -> datetime:
    if now.tzinfo is not None:
        return now.astimezone(IST)
    return now.replace(tzinfo=IST)


def is_market_open_now(now: datetime) -> bool:
    ist_now = _to_ist(now)
    if not is_trading_day(ist_now.date()):
        return False
    return MARKET_OPEN_TIME <= ist_now.time() <= MARKET_CLOSE_TIME


def next_market_open(now: datetime) -> datetime:
    ist_now = _to_ist(now)
    if is_market_open_now(ist_now):
        return ist_now

    candidate_date = ist_now.date()
    if is_trading_day(candidate_date) and ist_now.time() > MARKET_CLOSE_TIME:
        candidate_date += timedelta(days=1)
    elif not is_trading_day(candidate_date):
        candidate_date += timedelta(days=1)

    while not is_trading_day(candidate_date):
        candidate_date += timedelta(days=1)

    return datetime.combine(candidate_date, MARKET_OPEN_TIME, tzinfo=IST)


def seconds_until_next_open(now: datetime) -> float:
    ist_now = _to_ist(now)
    if is_market_open_now(ist_now):
        return 0.0
    return (next_market_open(ist_now) - ist_now).total_seconds()


def seconds_until_close(now: datetime) -> float:
    ist_now = _to_ist(now)
    if not is_market_open_now(ist_now):
        return 0.0
    close_dt = datetime.combine(ist_now.date(), MARKET_CLOSE_TIME, tzinfo=IST)
    return max((close_dt - ist_now).total_seconds(), 0.0)
