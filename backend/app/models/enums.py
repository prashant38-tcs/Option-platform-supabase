from enum import Enum, IntEnum


class TradingMode(str, Enum):
    ADVISORY = "ADVISORY"
    PAPER = "PAPER"
    LIVE = "LIVE"


class Underlying(str, Enum):
    NIFTY = "NIFTY50"
    BANKNIFTY = "NIFTYBANK"
    FINNIFTY = "FINNIFTY"
    SENSEX = "SENSEX"


class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"


class FyersOrderSide(IntEnum):
    BUY = 1
    SELL = -1


class FyersOrderType(IntEnum):
    LIMIT = 1
    MARKET = 2
    STOP_SL_M = 3
    STOP_LIMIT_SL_L = 4


class FyersProductType(str, Enum):
    CNC = "CNC"
    INTRADAY = "INTRADAY"
    MARGIN = "MARGIN"
    MTF = "MTF"


class FyersValidity(str, Enum):
    DAY = "DAY"
    IOC = "IOC"


class OrderLifecycleStatus(str, Enum):
    PENDING_RISK_CHECK = "PENDING_RISK_CHECK"
    REJECTED_BY_RISK = "REJECTED_BY_RISK"
    ADVISORY_ONLY = "ADVISORY_ONLY"
    SIMULATED_OPEN = "SIMULATED_OPEN"
    SIMULATED_CLOSED = "SIMULATED_CLOSED"
    SENT_TO_BROKER = "SENT_TO_BROKER"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    BROKER_REJECTED = "BROKER_REJECTED"
    ERRORED = "ERRORED"


class RiskCategory(str, Enum):
    DEFINED_RISK = "DEFINED_RISK"
    UNDEFINED_RISK = "UNDEFINED_RISK"


class StrategyType(str, Enum):
    LONG_CALL = "LONG_CALL"
    LONG_PUT = "LONG_PUT"
    COVERED_CALL = "COVERED_CALL"
    BULL_CALL_SPREAD = "BULL_CALL_SPREAD"
    BEAR_PUT_SPREAD = "BEAR_PUT_SPREAD"
    IRON_CONDOR = "IRON_CONDOR"
    SHORT_STRADDLE = "SHORT_STRADDLE"
    SHORT_STRANGLE = "SHORT_STRANGLE"
    LONG_STRADDLE = "LONG_STRADDLE"


class MarketRegime(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL_RANGE_BOUND = "NEUTRAL_RANGE_BOUND"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"


class LLMProvider(str, Enum):
    GROQ = "GROQ"
    GEMINI = "GEMINI"
