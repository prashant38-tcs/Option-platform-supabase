from __future__ import annotations
from datetime import datetime
from typing import Optional

from app.models.backtest_schemas import BacktestTrade, BacktestReport, StrategyPerformanceStats
from app.models.enums import StrategyType, RiskCategory
from app.models.quant_config import QuantAgentConfig


class PerformanceTracker:
    def __init__(self, drawdown_penalty_weight: float = 0.1):
        self._trades: list[tuple[BacktestTrade, str]] = []
        self._drawdown_penalty_weight = drawdown_penalty_weight

    def ingest_backtest_report(self, report: BacktestReport) -> None:
        for trade in report.trades:
            self._trades.append((trade, "backtest"))

    def ingest_live_trade(self, trade: BacktestTrade) -> None:
        self._trades.append((trade, "live_paper"))

    def _trades_for(self, strategy_type: StrategyType) -> list[BacktestTrade]:
        return [t for t, _ in self._trades if t.strategy_type == strategy_type]

    def _sources_for(self, strategy_type: StrategyType) -> list[str]:
        return sorted({src for t, src in self._trades if t.strategy_type == strategy_type})

    @staticmethod
    def _max_drawdown_pct(trades: list[BacktestTrade], portfolio_capital_base: float) -> float:
        if not trades or portfolio_capital_base <= 0:
            return 0.0
        ordered = sorted(trades, key=lambda t: t.exit_date)
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in ordered:
            cumulative += t.realized_pnl
            peak = max(peak, cumulative)
            drawdown = ((cumulative - peak) / portfolio_capital_base) * 100.0
            max_dd = min(max_dd, drawdown)
        return round(max_dd, 3)

    def compute_stats(self, portfolio_capital_base: Optional[float] = None, now: Optional[datetime] = None) -> dict[StrategyType, StrategyPerformanceStats]:
        now = now or datetime.utcnow()
        results: dict[StrategyType, StrategyPerformanceStats] = {}
        strategy_types = {t.strategy_type for t, _ in self._trades}

        if portfolio_capital_base is None:
            all_trades = [t for t, _ in self._trades]
            if all_trades:
                avg_all = sum(t.capital_deployed for t in all_trades) / len(all_trades)
                portfolio_capital_base = avg_all * 10
            else:
                portfolio_capital_base = 1.0

        for st in strategy_types:
            trades = self._trades_for(st)
            n = len(trades)
            if n == 0:
                continue
            wins = sum(1 for t in trades if t.is_win)
            win_rate = wins / n
            avg_pnl = sum(t.realized_pnl for t in trades) / n
            avg_return_pct = sum(t.return_pct_on_capital for t in trades) / n
            total_pnl = sum(t.realized_pnl for t in trades)
            max_dd = self._max_drawdown_pct(trades, portfolio_capital_base)
            composite_score = (avg_return_pct * win_rate) - (self._drawdown_penalty_weight * abs(max_dd))

            results[st] = StrategyPerformanceStats(
                strategy_type=st, risk_category=trades[0].risk_category, sample_size=n,
                win_rate=round(win_rate, 4), avg_pnl_per_trade=round(avg_pnl, 2),
                avg_return_pct_on_capital=round(avg_return_pct, 3), max_drawdown_pct=max_dd,
                total_pnl=round(total_pnl, 2), composite_score=round(composite_score, 4),
                computed_at=now, data_sources_included=self._sources_for(st),
            )
        return results

    def annotate_signal(self, signal, config: QuantAgentConfig, portfolio_capital_base: Optional[float] = None) -> None:
        if not config.use_performance_feedback:
            return
        stats = self.compute_stats(portfolio_capital_base=portfolio_capital_base)
        st_stats = stats.get(signal.strategy_type)
        if st_stats is None or st_stats.sample_size < config.min_sample_size_for_feedback:
            signal.performance_note = (f"Insufficient historical data ({st_stats.sample_size if st_stats else 0} trades, "
                                         f"need {config.min_sample_size_for_feedback}) -- confidence score not yet available.")
            return

        signal.confidence_score = st_stats.composite_score
        signal.historical_win_rate = st_stats.win_rate
        signal.historical_sample_size = st_stats.sample_size
        if st_stats.composite_score < config.low_confidence_score_threshold:
            signal.performance_note = (f"LOW CONFIDENCE: this strategy type has historically underperformed "
                                         f"(win rate {st_stats.win_rate:.0%}, composite score {st_stats.composite_score:.2f} "
                                         f"over {st_stats.sample_size} trades). Still shown per platform policy -- review carefully.")
        else:
            signal.performance_note = (f"Historical win rate {st_stats.win_rate:.0%} over {st_stats.sample_size} trades "
                                         f"(composite score {st_stats.composite_score:.2f}).")

    def rank_candidates(self, signals: list, config: QuantAgentConfig, portfolio_capital_base: Optional[float] = None) -> list:
        for sig in signals:
            self.annotate_signal(sig, config, portfolio_capital_base=portfolio_capital_base)

        defined = [s for s in signals if s.risk_category == RiskCategory.DEFINED_RISK]
        undefined = [s for s in signals if s.risk_category == RiskCategory.UNDEFINED_RISK]

        def sort_key(s):
            return s.confidence_score if s.confidence_score is not None else 0.0

        defined.sort(key=sort_key, reverse=True)
        undefined.sort(key=sort_key, reverse=True)

        if signals and signals[0].risk_category == RiskCategory.DEFINED_RISK:
            return defined + undefined
        return undefined + defined
