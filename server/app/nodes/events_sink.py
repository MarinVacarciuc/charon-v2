"""Wires the poller's Events protocol to the two things that actually need to know:
the audit log (for the report and for anyone reviewing what happened) and the SSE hub
(for anything watching live, starting with the dashboard).

Kept separate from NodePoller itself so the poller can be unit-tested and bench-run with no
database or hub at all, as it already was in tools/ during development.
"""
from __future__ import annotations

import logging

from ..db.database import Database
from ..db.repositories import audit
from ..push import events as ev
from ..push.hub import SseHub
from .state import NodeLive

log = logging.getLogger(__name__)


class BrainEvents:
    def __init__(self, db: Database, hub: SseHub) -> None:
        self._db = db
        self._hub = hub

    async def node_online(self, node: NodeLive) -> None:
        await audit.record(self._db, "node_online", f"{node.node_id} online",
                           severity="info", node_id=node.node_id)
        await self._hub.publish(ev.node_status(node.node_id, online=True, cam_on=node.cam_on))

    async def node_offline(self, node: NodeLive, reason: str) -> None:
        # Matches the old build's stance, carried forward deliberately: a node going dark is a
        # security event (tamper/jam), not a glitch, so it is severity=alert, not warn.
        await audit.record(self._db, "node_offline", f"{node.node_id} offline: {reason}",
                           severity="alert", node_id=node.node_id, details={"reason": reason})
        await self._hub.publish(ev.node_status(node.node_id, online=False, cam_on=False, reason=reason))

    async def node_status(self, node: NodeLive) -> None:
        # Deliberately NOT audited or pushed on every poll (3 Hz x six nodes would flood
        # both). Callers that want live sensor values read NodeLive directly via /nodes.
        pass

    async def frame(self, node: NodeLive, jpeg: bytes) -> None:
        pass

    async def passage(self, node: NodeLive, count: int) -> None:
        await audit.record(self._db, "passage", f"{node.node_id} passage #{count}",
                           node_id=node.node_id, details={"count": count})
        await self._hub.publish(ev.passage(node.node_id, node.direction, count))
