from __future__ import annotations
from datetime import datetime
from typing import Optional
import uuid

from app.models.enums import Underlying, OptionType, StrategyType, RiskCategory, FyersOrderSide
from app.models.market_schemas import OptionChainSnapshot, OptionChainItem
from app.models.strategy_schemas import StrategyLeg, TradeSignal
from app.core.lot_sizes import get_lot_size


def _find_strike(items: list[OptionChainItem], target_strike: float) -> Optional[OptionChainItem]:
    for item in items:
        if abs(item.strike - target_strike) < 1e-6:
            return item
    return None


def _make_leg(item: OptionChainItem, side: FyersOrderSide, lots: int, underlying: Underlying, expiry: datetime) -> StrategyLeg:
    return StrategyLeg(underlying=underlying, expiry=expiry, strike=item.strike, option_type=item.option_type,
                         side=side, lots=lots, lot_size=get_lot_size(underlying), symbol=item.symbol,
                         entry_price_hint=item.mid_price, greeks_at_signal=item.greeks)


def _new_signal_id() -> str:
    return f"sig-{uuid.uuid4().hex[:12]}"


def build_bull_call_spread(snapshot: OptionChainSnapshot, long_strike: float, short_strike: float, lots: int = 1) -> Optional[TradeSignal]:
    if short_strike <= long_strike:
        raise ValueError("short_strike must be > long_strike for a bull call spread")
    long_leg_item = _find_strike(snapshot.calls, long_strike)
    short_leg_item = _find_strike(snapshot.calls, short_strike)
    if not long_leg_item or not short_leg_item:
        return None

    lot_size = get_lot_size(snapshot.underlying)
    net_debit_per_unit = long_leg_item.mid_price - short_leg_item.mid_price
    if net_debit_per_unit <= 0:
        return None

    strike_width = short_strike - long_strike
    max_loss = net_debit_per_unit * lots * lot_size
    max_profit = (strike_width - net_debit_per_unit) * lots * lot_size
    breakeven = long_strike + net_debit_per_unit

    legs = [_make_leg(long_leg_item, FyersOrderSide.BUY, lots, snapshot.underlying, snapshot.expiry),
            _make_leg(short_leg_item, FyersOrderSide.SELL, lots, snapshot.underlying, snapshot.expiry)]
    return TradeSignal(signal_id=_new_signal_id(), generated_at=snapshot.fetched_at, underlying=snapshot.underlying,
                         strategy_type=StrategyType.BULL_CALL_SPREAD, risk_category=RiskCategory.DEFINED_RISK,
                         legs=legs, rationale=f"Bullish defined-risk spread: long {long_strike}CE / short {short_strike}CE",
                         max_loss_estimate=round(max_loss, 2), max_profit_estimate=round(max_profit, 2),
                         breakeven_points=[round(breakeven, 2)], net_premium=round(-net_debit_per_unit * lots * lot_size, 2))


def build_bear_put_spread(snapshot: OptionChainSnapshot, long_strike: float, short_strike: float, lots: int = 1) -> Optional[TradeSignal]:
    if long_strike <= short_strike:
        raise ValueError("long_strike must be > short_strike for a bear put spread")
    long_leg_item = _find_strike(snapshot.puts, long_strike)
    short_leg_item = _find_strike(snapshot.puts, short_strike)
    if not long_leg_item or not short_leg_item:
        return None

    lot_size = get_lot_size(snapshot.underlying)
    net_debit_per_unit = long_leg_item.mid_price - short_leg_item.mid_price
    if net_debit_per_unit <= 0:
        return None

    strike_width = long_strike - short_strike
    max_loss = net_debit_per_unit * lots * lot_size
    max_profit = (strike_width - net_debit_per_unit) * lots * lot_size
    breakeven = long_strike - net_debit_per_unit

    legs = [_make_leg(long_leg_item, FyersOrderSide.BUY, lots, snapshot.underlying, snapshot.expiry),
            _make_leg(short_leg_item, FyersOrderSide.SELL, lots, snapshot.underlying, snapshot.expiry)]
    return TradeSignal(signal_id=_new_signal_id(), generated_at=snapshot.fetched_at, underlying=snapshot.underlying,
                         strategy_type=StrategyType.BEAR_PUT_SPREAD, risk_category=RiskCategory.DEFINED_RISK,
                         legs=legs, rationale=f"Bearish defined-risk spread: long {long_strike}PE / short {short_strike}PE",
                         max_loss_estimate=round(max_loss, 2), max_profit_estimate=round(max_profit, 2),
                         breakeven_points=[round(breakeven, 2)], net_premium=round(-net_debit_per_unit * lots * lot_size, 2))


def build_iron_condor(snapshot: OptionChainSnapshot, put_long_strike: float, put_short_strike: float,
                        call_short_strike: float, call_long_strike: float, lots: int = 1) -> Optional[TradeSignal]:
    if not (put_long_strike < put_short_strike < call_short_strike < call_long_strike):
        raise ValueError("Strikes must satisfy put_long < put_short < call_short < call_long")

    put_long = _find_strike(snapshot.puts, put_long_strike)
    put_short = _find_strike(snapshot.puts, put_short_strike)
    call_short = _find_strike(snapshot.calls, call_short_strike)
    call_long = _find_strike(snapshot.calls, call_long_strike)
    if not all([put_long, put_short, call_short, call_long]):
        return None

    lot_size = get_lot_size(snapshot.underlying)
    net_credit_per_unit = (put_short.mid_price - put_long.mid_price + call_short.mid_price - call_long.mid_price)
    if net_credit_per_unit <= 0:
        return None

    put_wing_width = put_short_strike - put_long_strike
    call_wing_width = call_long_strike - call_short_strike
    wider_wing = max(put_wing_width, call_wing_width)

    max_loss = (wider_wing - net_credit_per_unit) * lots * lot_size
    max_profit = net_credit_per_unit * lots * lot_size
    lower_breakeven = put_short_strike - net_credit_per_unit
    upper_breakeven = call_short_strike + net_credit_per_unit

    legs = [_make_leg(put_long, FyersOrderSide.BUY, lots, snapshot.underlying, snapshot.expiry),
            _make_leg(put_short, FyersOrderSide.SELL, lots, snapshot.underlying, snapshot.expiry),
            _make_leg(call_short, FyersOrderSide.SELL, lots, snapshot.underlying, snapshot.expiry),
            _make_leg(call_long, FyersOrderSide.BUY, lots, snapshot.underlying, snapshot.expiry)]
    return TradeSignal(signal_id=_new_signal_id(), generated_at=snapshot.fetched_at, underlying=snapshot.underlying,
                         strategy_type=StrategyType.IRON_CONDOR, risk_category=RiskCategory.DEFINED_RISK, legs=legs,
                         rationale=(f"Neutral defined-risk range trade: put spread {put_long_strike}/{put_short_strike}, "
                                    f"call spread {call_short_strike}/{call_long_strike}"),
                         max_loss_estimate=round(max_loss, 2), max_profit_estimate=round(max_profit, 2),
                         breakeven_points=[round(lower_breakeven, 2), round(upper_breakeven, 2)],
                         net_premium=round(net_credit_per_unit * lots * lot_size, 2))


def build_long_straddle(snapshot: OptionChainSnapshot, strike: float, lots: int = 1) -> Optional[TradeSignal]:
    call_item = _find_strike(snapshot.calls, strike)
    put_item = _find_strike(snapshot.puts, strike)
    if not call_item or not put_item:
        return None

    lot_size = get_lot_size(snapshot.underlying)
    net_debit_per_unit = call_item.mid_price + put_item.mid_price
    max_loss = net_debit_per_unit * lots * lot_size
    upper_breakeven = strike + net_debit_per_unit
    lower_breakeven = strike - net_debit_per_unit

    legs = [_make_leg(call_item, FyersOrderSide.BUY, lots, snapshot.underlying, snapshot.expiry),
            _make_leg(put_item, FyersOrderSide.BUY, lots, snapshot.underlying, snapshot.expiry)]
    return TradeSignal(signal_id=_new_signal_id(), generated_at=snapshot.fetched_at, underlying=snapshot.underlying,
                         strategy_type=StrategyType.LONG_STRADDLE, risk_category=RiskCategory.DEFINED_RISK, legs=legs,
                         rationale=f"Long volatility play at ATM strike {strike}, expecting a large move",
                         max_loss_estimate=round(max_loss, 2), max_profit_estimate=None,
                         breakeven_points=[round(lower_breakeven, 2), round(upper_breakeven, 2)],
                         net_premium=round(-net_debit_per_unit * lots * lot_size, 2))


def build_short_straddle(snapshot: OptionChainSnapshot, strike: float, lots: int = 1) -> Optional[TradeSignal]:
    call_item = _find_strike(snapshot.calls, strike)
    put_item = _find_strike(snapshot.puts, strike)
    if not call_item or not put_item:
        return None

    lot_size = get_lot_size(snapshot.underlying)
    net_credit_per_unit = call_item.mid_price + put_item.mid_price
    upper_breakeven = strike + net_credit_per_unit
    lower_breakeven = strike - net_credit_per_unit

    legs = [_make_leg(call_item, FyersOrderSide.SELL, lots, snapshot.underlying, snapshot.expiry),
            _make_leg(put_item, FyersOrderSide.SELL, lots, snapshot.underlying, snapshot.expiry)]
    return TradeSignal(signal_id=_new_signal_id(), generated_at=snapshot.fetched_at, underlying=snapshot.underlying,
                         strategy_type=StrategyType.SHORT_STRADDLE, risk_category=RiskCategory.UNDEFINED_RISK, legs=legs,
                         rationale=f"Naked short volatility at ATM {strike} -- expects range-bound expiry. UNDEFINED RISK.",
                         max_loss_estimate=None, max_profit_estimate=round(net_credit_per_unit * lots * lot_size, 2),
                         breakeven_points=[round(lower_breakeven, 2), round(upper_breakeven, 2)],
                         net_premium=round(net_credit_per_unit * lots * lot_size, 2))


def build_short_strangle(snapshot: OptionChainSnapshot, put_strike: float, call_strike: float, lots: int = 1) -> Optional[TradeSignal]:
    if put_strike >= call_strike:
        raise ValueError("put_strike must be < call_strike for a short strangle")
    put_item = _find_strike(snapshot.puts, put_strike)
    call_item = _find_strike(snapshot.calls, call_strike)
    if not put_item or not call_item:
        return None

    lot_size = get_lot_size(snapshot.underlying)
    net_credit_per_unit = put_item.mid_price + call_item.mid_price
    upper_breakeven = call_strike + net_credit_per_unit
    lower_breakeven = put_strike - net_credit_per_unit

    legs = [_make_leg(put_item, FyersOrderSide.SELL, lots, snapshot.underlying, snapshot.expiry),
            _make_leg(call_item, FyersOrderSide.SELL, lots, snapshot.underlying, snapshot.expiry)]
    return TradeSignal(signal_id=_new_signal_id(), generated_at=snapshot.fetched_at, underlying=snapshot.underlying,
                         strategy_type=StrategyType.SHORT_STRANGLE, risk_category=RiskCategory.UNDEFINED_RISK, legs=legs,
                         rationale=f"Naked short strangle {put_strike}PE/{call_strike}CE -- wide range bet. UNDEFINED RISK.",
                         max_loss_estimate=None, max_profit_estimate=round(net_credit_per_unit * lots * lot_size, 2),
                         breakeven_points=[round(lower_breakeven, 2), round(upper_breakeven, 2)],
                         net_premium=round(net_credit_per_unit * lots * lot_size, 2))


def build_long_call(snapshot: OptionChainSnapshot, strike: float, lots: int = 1) -> Optional[TradeSignal]:
    item = _find_strike(snapshot.calls, strike)
    if not item:
        return None
    lot_size = get_lot_size(snapshot.underlying)
    max_loss = item.mid_price * lots * lot_size
    breakeven = strike + item.mid_price
    legs = [_make_leg(item, FyersOrderSide.BUY, lots, snapshot.underlying, snapshot.expiry)]
    return TradeSignal(signal_id=_new_signal_id(), generated_at=snapshot.fetched_at, underlying=snapshot.underlying,
                         strategy_type=StrategyType.LONG_CALL, risk_category=RiskCategory.DEFINED_RISK, legs=legs,
                         rationale=f"Bullish directional long call at {strike}", max_loss_estimate=round(max_loss, 2),
                         max_profit_estimate=None, breakeven_points=[round(breakeven, 2)], net_premium=round(-max_loss, 2))


def build_long_put(snapshot: OptionChainSnapshot, strike: float, lots: int = 1) -> Optional[TradeSignal]:
    item = _find_strike(snapshot.puts, strike)
    if not item:
        return None
    lot_size = get_lot_size(snapshot.underlying)
    max_loss = item.mid_price * lots * lot_size
    breakeven = strike - item.mid_price
    legs = [_make_leg(item, FyersOrderSide.BUY, lots, snapshot.underlying, snapshot.expiry)]
    return TradeSignal(signal_id=_new_signal_id(), generated_at=snapshot.fetched_at, underlying=snapshot.underlying,
                         strategy_type=StrategyType.LONG_PUT, risk_category=RiskCategory.DEFINED_RISK, legs=legs,
                         rationale=f"Bearish directional long put at {strike}", max_loss_estimate=round(max_loss, 2),
                         max_profit_estimate=None, breakeven_points=[round(breakeven, 2)], net_premium=round(-max_loss, 2))
