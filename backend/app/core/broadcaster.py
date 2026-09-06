from __future__ import annotations
import asyncio
import logging
from collections import defaultdict
from typing import Any

from app.models.enums import Underlying

logger = logging.getLogger("broadcaster")

_QUEUE_MAX_SIZE = 200


class EventBroadcaster:
    def __init__(self):
        self._subscribers: dict[Underlying, set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, underlying: Underlying) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX_SIZE)
        async with self._lock:
            self._subscribers[underlying].add(queue)
        return queue

    async def unsubscribe(self, underlying: Underlying, queue: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers[underlying].discard(queue)

    async def publish(self, underlying: Underlying, message: dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(underlying, ()))
        for q in queues:
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("Broadcaster queue still full after drop-oldest for %s -- message dropped.", underlying.value)

    def subscriber_count(self, underlying: Underlying) -> int:
        return len(self._subscribers.get(underlying, ()))
