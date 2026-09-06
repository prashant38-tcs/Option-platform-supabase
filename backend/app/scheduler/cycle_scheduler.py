from __future__ import annotations
import asyncio
import logging
import traceback
from collections import deque
from datetime import datetime
from typing import Callable, Optional

from app.core.market_calendar import is_market_open_now, seconds_until_next_open, next_market_open, now_ist_naive
from app.graph.workflow import WorkflowAgents, run_cycle
from app.models.agent_state import TradingWorkflowState
from app.models.enums import Underlying, TradingMode
from app.models.scheduler_schemas import CycleSummary, UnderlyingScheduleStatus, SchedulerStatus

logger = logging.getLogger("cycle_scheduler")

_MAX_MARKET_CLOSED_SLEEP_CHUNK_SECONDS = 30.0
_MAX_HISTORY_PER_UNDERLYING = 200


class CycleScheduler:
    def __init__(self, compiled_graph, agents_by_underlying: dict, mode_provider: Callable[[Underlying], TradingMode],
                 interval_seconds: float = 60, market_hours_only: bool = True,
                 shared_risk_lock: Optional[asyncio.Lock] = None, broadcaster=None):
        self._graph = compiled_graph
        self._agents_by_underlying = agents_by_underlying
        self._mode_provider = mode_provider
        self._interval_seconds = interval_seconds
        self._market_hours_only = market_hours_only
        self._shared_risk_lock = shared_risk_lock
        self._broadcaster = broadcaster

        self._tasks: dict[Underlying, asyncio.Task] = {}
        self._running: dict[Underlying, bool] = {u: False for u in agents_by_underlying}
        self._history: dict[Underlying, deque] = {u: deque(maxlen=_MAX_HISTORY_PER_UNDERLYING) for u in agents_by_underlying}
        self._total_cycles: dict[Underlying, int] = {u: 0 for u in agents_by_underlying}
        self._total_errors: dict[Underlying, int] = {u: 0 for u in agents_by_underlying}
        self._last_cycle_at: dict[Underlying, Optional[datetime]] = {u: None for u in agents_by_underlying}
        self._next_cycle_at: dict[Underlying, Optional[datetime]] = {u: None for u in agents_by_underlying}

    def start(self) -> None:
        for underlying in self._agents_by_underlying:
            if self._running.get(underlying):
                continue
            self._running[underlying] = True
            self._tasks[underlying] = asyncio.create_task(self._run_loop(underlying), name=f"cycle-scheduler-{underlying.value}")
        logger.info("CycleScheduler started for underlyings: %s", [u.value for u in self._agents_by_underlying])

    async def stop(self, timeout: float = 10.0) -> None:
        for underlying in list(self._tasks.keys()):
            self._running[underlying] = False
            self._tasks[underlying].cancel()
        if self._tasks:
            await asyncio.wait(list(self._tasks.values()), timeout=timeout)
        self._tasks.clear()
        logger.info("CycleScheduler stopped.")

    def start_underlying(self, underlying: Underlying) -> None:
        if underlying not in self._agents_by_underlying:
            raise ValueError(f"{underlying} was not configured in this scheduler's agents_by_underlying")
        if self._running.get(underlying):
            return
        self._running[underlying] = True
        self._tasks[underlying] = asyncio.create_task(self._run_loop(underlying), name=f"cycle-scheduler-{underlying.value}")

    async def stop_underlying(self, underlying: Underlying, timeout: float = 10.0) -> None:
        self._running[underlying] = False
        task = self._tasks.pop(underlying, None)
        if task:
            task.cancel()
            await asyncio.wait([task], timeout=timeout)

    async def run_now(self, underlying: Underlying) -> CycleSummary:
        return await self._execute_one_cycle(underlying)

    async def _run_loop(self, underlying: Underlying) -> None:
        try:
            while self._running.get(underlying):
                now = now_ist_naive()
                if self._market_hours_only and not is_market_open_now(now):
                    wait_seconds = min(seconds_until_next_open(now), _MAX_MARKET_CLOSED_SLEEP_CHUNK_SECONDS)
                    self._next_cycle_at[underlying] = None
                    await asyncio.sleep(max(wait_seconds, 1.0))
                    continue

                await self._execute_one_cycle(underlying)

                if not self._running.get(underlying):
                    break
                self._next_cycle_at[underlying] = now_ist_naive()
                await asyncio.sleep(self._interval_seconds)
        except asyncio.CancelledError:
            logger.info("Cycle loop for %s cancelled cleanly.", underlying.value)
            raise
        finally:
            self._running[underlying] = False

    async def _execute_one_cycle(self, underlying: Underlying) -> CycleSummary:
        agents: WorkflowAgents = self._agents_by_underlying[underlying]
        trading_mode = self._mode_provider(underlying)
        now = now_ist_naive()
        cycle_id = f"{underlying.value}-{now.strftime('%Y%m%d%H%M%S')}"

        initial_state = TradingWorkflowState(cycle_id=cycle_id, underlying=underlying, trading_mode=trading_mode, started_at=now)

        async def _do_run() -> TradingWorkflowState:
            return await run_cycle(self._graph, agents, initial_state, broadcaster=self._broadcaster)

        try:
            if self._shared_risk_lock is not None:
                async with self._shared_risk_lock:
                    final_state = await _do_run()
            else:
                final_state = await _do_run()

            summary = CycleSummary(
                cycle_id=final_state.cycle_id, underlying=underlying, trading_mode=trading_mode,
                started_at=final_state.started_at, completed_at=final_state.completed_at,
                cycle_status=final_state.cycle_status, halt_or_error_reason=final_state.halt_or_error_reason,
                num_candidate_signals=len(final_state.candidate_signals), num_approved_signals=len(final_state.approved_signals),
                num_orders_created=len(final_state.orders_created),
                daily_pnl_at_completion=(final_state.daily_risk_state.total_pnl_today if final_state.daily_risk_state else None),
            )
        except Exception as exc:
            logger.error("Unhandled exception during cycle for %s: %s\n%s", underlying.value, exc, traceback.format_exc())
            summary = CycleSummary(cycle_id=cycle_id, underlying=underlying, trading_mode=trading_mode,
                                     started_at=now, completed_at=now_ist_naive(), cycle_status="errored",
                                     halt_or_error_reason=f"Unhandled exception: {exc}")
            self._total_errors[underlying] += 1
            if self._broadcaster is not None:
                await self._broadcaster.publish(underlying, {"type": "cycle_error", "message": str(exc)})

        self._total_cycles[underlying] += 1
        self._last_cycle_at[underlying] = summary.completed_at or now
        self._history[underlying].append(summary)
        if self._broadcaster is not None:
            await self._broadcaster.publish(underlying, {"type": "cycle_summary", "data": summary.model_dump(mode="json")})
        return summary

    def get_recent_cycles(self, underlying: Underlying, n: int = 20) -> list[CycleSummary]:
        history = self._history.get(underlying, deque())
        return list(history)[-n:]

    def get_status(self) -> SchedulerStatus:
        now = now_ist_naive()
        underlying_statuses = []
        any_running = False
        for underlying in self._agents_by_underlying:
            running = self._running.get(underlying, False)
            any_running = any_running or running
            history = self._history.get(underlying, deque())
            last = history[-1] if history else None
            underlying_statuses.append(UnderlyingScheduleStatus(
                underlying=underlying, is_running=running, is_market_open=is_market_open_now(now),
                trading_mode=self._mode_provider(underlying), total_cycles_run=self._total_cycles.get(underlying, 0),
                total_errors=self._total_errors.get(underlying, 0), last_cycle_at=self._last_cycle_at.get(underlying),
                last_cycle_status=last.cycle_status if last else None, next_cycle_at=self._next_cycle_at.get(underlying),
                next_market_open_at=None if is_market_open_now(now) else next_market_open(now),
            ))
        return SchedulerStatus(is_scheduler_running=any_running, interval_seconds=self._interval_seconds,
                                 market_hours_only=self._market_hours_only, underlyings=underlying_statuses)
