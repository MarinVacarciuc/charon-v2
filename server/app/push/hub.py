"""SSE broadcast hub: one asyncio.Queue per connected client, fan-out on publish.

Chosen over WebSockets deliberately (see docs/BUILD_PLAN.md): EventSource reconnects on its
own, which matters more than a bidirectional channel here, since every admin action is
already a plain request/response and the only thing flowing the other way is status.
"""
from __future__ import annotations

import asyncio
import json
import logging

log = logging.getLogger(__name__)

QUEUE_MAXSIZE = 100  # a client that falls this far behind is disconnected, not backlogged forever


class SseHub:
    def __init__(self) -> None:
        self._clients: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._clients.discard(q)

    async def publish(self, event: dict) -> None:
        dead: list[asyncio.Queue] = []
        for q in self._clients:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # A slow client (a stalled browser tab) must not be allowed to apply
                # backpressure to everyone else's events. Drop it rather than the events.
                dead.append(q)
        for q in dead:
            log.warning("SSE client fell too far behind, dropping it")
            self._clients.discard(q)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @staticmethod
    def format_sse(event: dict) -> str:
        return f"data: {json.dumps(event)}\n\n"
