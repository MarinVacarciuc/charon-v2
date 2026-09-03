"""Turns the `nodes` table into a running fleet of supervised pollers.

This is the seam between configuration (what an operator set up, persisted in SQLite) and
runtime (what is actually happening right now, in memory). Loading is one-way at startup;
nothing here watches the table for live edits, because no part of the system edits it yet.
"""
from __future__ import annotations

import asyncio
import logging

import aiohttp

from ..db.database import Database
from .poller import Events, NodePoller, supervise
from .resolver import Ipv4Resolver
from .state import NodeLive

log = logging.getLogger(__name__)


class NodeRegistry:
    def __init__(self, db: Database, session: aiohttp.ClientSession, events: Events | None = None) -> None:
        self._db = db
        self._session = session
        self._resolver = Ipv4Resolver()
        self._events = events
        self._live: dict[str, NodeLive] = {}
        self._tasks: list[asyncio.Task] = []

    def get(self, node_id: str) -> NodeLive | None:
        return self._live.get(node_id)

    def all(self) -> list[NodeLive]:
        return list(self._live.values())

    async def load(self) -> None:
        """Read every enabled node from the database and build its live-state object.

        Idempotent-ish in the sense that calling it twice would duplicate entries, but there
        is exactly one call site (startup), so that is not a case worth guarding.
        """
        rows = await self._db.fetch_all(
            """
            SELECT n.id, n.label, n.role, n.hostname, n.rotation_deg,
                   z.name AS zone_name
            FROM nodes n
            LEFT JOIN zones z ON z.id = n.zone_id
            WHERE n.enabled = 1
            ORDER BY n.rowid
            """
        )
        for row in rows:
            self._live[row["id"]] = NodeLive(
                node_id=row["id"],
                hostname=row["hostname"],
                role=row["role"],
                zone=row["zone_name"],
                rotation_deg=row["rotation_deg"],
            )
        log.info("loaded %d node(s) from the registry: %s", len(self._live), list(self._live))

    async def start(self) -> None:
        """Start one supervised poller task per node. Safe to call once, after load()."""
        if not self._live:
            await self.load()
        for live in self._live.values():
            poller = NodePoller(live, self._session, self._resolver, self._events)
            task = asyncio.create_task(supervise(poller, on_crash=self._log_crash), name=f"poll:{live.node_id}")
            self._tasks.append(task)
        log.info("started %d poller task(s)", len(self._tasks))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _log_crash(self, live: NodeLive, exc: BaseException) -> None:
        # Best-effort: a database problem here must not take down the supervisor loop that is
        # trying to recover from a DIFFERENT problem.
        try:
            from ..db.database import utcnow

            await self._db.execute(
                "INSERT INTO audit_log (ts, actor, event_type, severity, node_id, message, details_json) "
                "VALUES (?, 'system', 'poller_crash', 'warn', ?, ?, '{}')",
                (utcnow(), live.node_id, f"poller for {live.node_id} crashed: {exc!r}"),
            )
        except Exception:  # noqa: BLE001
            log.exception("failed to audit-log a poller crash for %s", live.node_id)
