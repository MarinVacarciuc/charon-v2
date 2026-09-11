"""One polling task per node, plus a supervisor that will not let one die quietly.

This module is written against a specific, expensive failure from the previous build. A
variable was assigned only after a fallible call and then read inside that call's `except`.
When the call failed on the first pass, the handler raised a second exception while handling
the first, the task died, and the node read OFFLINE forever with nothing in the log to say
why. Four of six camera workers died that way in one afternoon.

Three rules follow from that, and they are structural rather than a matter of care:

  1. Every name an `except` reads is bound before the `try`. There is nothing a handler can
     reference that might not exist yet.
  2. Network failure and processing failure are separate blocks with separate consequences.
     A node that cannot be reached is offline. A node whose frame could not be decoded is
     still online, keeps its last good state, and gets logged - a bug in our own processing
     must never be able to report healthy hardware as dead.
  3. Every task runs under a supervisor that catches everything, records it, waits, and
     restarts. "Silently dead forever" has to be impossible to express, not merely unlikely.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable, Protocol

import aiohttp

from .frames import rotate_jpeg
from .resolver import Ipv4Resolver
from .state import NodeLive

log = logging.getLogger(__name__)

STATUS_INTERVAL_S = 0.33      # ~3 Hz: fast enough that a passage counter cannot be missed
OFFLINE_AFTER_S = 6.0         # matches the old build's threshold; a node dark this long is an event
# Split, because the two endpoints have very different jobs. /status touches no hardware and
# was measured at 20 ms median, 67 ms worst, so 1.5 s is a 20x margin on the worst case while
# still failing fast: how quickly a dead board is noticed is bounded by this. /shot.jpg may
# have to power the camera up first, which is about 950 ms on its own, so it gets room.
STATUS_TIMEOUT_S = 1.5
FRAME_TIMEOUT_S = 5.0
SUPERVISOR_BACKOFF_S = 2.0
# How many failures against a known address before we stop trusting it and resolve again.
# Resolving a name nobody answers costs the full mDNS timeout, so while a node is down we
# keep hammering its last address instead: a TCP connection to a dead host fails in
# milliseconds, which is what makes an unplugged board show as OFFLINE in seconds rather
# than in tens of seconds. Only a node that has genuinely moved needs a fresh lookup.
RERESOLVE_AFTER_FAILURES = 10


class Events(Protocol):
    """What the poller reports upward. Kept narrow so the poller has no idea whether anything
    is listening, which is what lets it be tested without a server."""

    async def node_online(self, node: NodeLive) -> None: ...
    async def node_offline(self, node: NodeLive, reason: str) -> None: ...
    async def node_status(self, node: NodeLive) -> None: ...
    async def frame(self, node: NodeLive, jpeg: bytes) -> None: ...
    async def passage(self, node: NodeLive, count: int) -> None: ...


class NullEvents:
    """Default sink. Useful on its own for bench runs."""

    async def node_online(self, node: NodeLive) -> None: ...
    async def node_offline(self, node: NodeLive, reason: str) -> None: ...
    async def node_status(self, node: NodeLive) -> None: ...
    async def frame(self, node: NodeLive, jpeg: bytes) -> None: ...
    async def passage(self, node: NodeLive, count: int) -> None: ...


class NodePoller:
    def __init__(
        self,
        live: NodeLive,
        session: aiohttp.ClientSession,
        resolver: Ipv4Resolver,
        events: Events | None = None,
    ) -> None:
        self.live = live
        self._session = session
        self._resolver = resolver
        self._events: Events = events or NullEvents()
        self._last_ip: str | None = None

    # ------------------------------------------------------------------ http

    async def _get(self, ip: str, path: str, timeout_s: float) -> tuple[int, dict[str, str], bytes]:
        # Connect to the literal IP so aiohttp's own resolver never runs; the Host header is
        # irrelevant to these boards, which serve one site.
        url = f"http://{ip}{path}"
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with self._session.get(url, timeout=timeout) as resp:
            body = await resp.read()
            return resp.status, dict(resp.headers), body

    # ------------------------------------------------------------------ state transitions

    async def _mark_offline(self, reason: str) -> None:
        self.live.consecutive_errors += 1
        self.live.last_error = reason
        # Only announce once, and only after the grace period: a single dropped poll on a
        # phone hotspot is normal and must not raise a security event.
        if self.live.online and self.live.age_s() > OFFLINE_AFTER_S:
            self.live.online = False
            self.live.cam_on = False
            log.warning("node %s offline: %s", self.live.node_id, reason)
            await self._events.node_offline(self.live, reason)

    async def _mark_online(self) -> None:
        self.live.last_seen = time.monotonic()
        self.live.consecutive_errors = 0
        self.live.last_error = ""
        if not self.live.online:
            self.live.online = True
            log.info("node %s online", self.live.node_id)
            await self._events.node_online(self.live)

    async def _apply_status(self, status: dict[str, Any]) -> None:
        live = self.live
        live.last_status = status
        live.cam_on = bool(status.get("cam_on"))
        live.near = bool(status.get("near"))
        live.near_cm = float(status.get("near_cm", -1.0))
        live.pass_cm = float(status.get("pass_cm", -1.0))

        count = status.get("passages")
        if isinstance(count, int) and live.is_gate:
            previous = live.passages
            live.passages = count
            if previous is None:
                # First reading only establishes the baseline. Treating it as traffic would
                # invent a passage for every gate on every restart of the brain.
                pass
            elif count > previous:
                # The counter is cumulative, so a jump of two means two bodies crossed, not
                # one event missed. Report each.
                for _ in range(count - previous):
                    await self._events.passage(live, count)
            elif count < previous:
                # Counters only fall when the board reboots. Re-baseline silently rather than
                # reporting a negative crossing.
                log.info("node %s passage counter reset (%d -> %d), re-baselining",
                         live.node_id, previous, count)

    # ------------------------------------------------------------------ the loop

    async def poll_once(self) -> None:
        # Everything an `except` below might touch is bound here, before anything can fail.
        host = self.live.hostname
        node_id = self.live.node_id
        ip: str | None = None
        status: dict[str, Any] | None = None

        # --- block 1: reaching the node at all. Failure here means offline. ---
        try:
            ip = await self._resolver.resolve(host)
            if ip is None:
                await self._mark_offline(f"{host} did not resolve")
                return
            self._last_ip = ip
            code, _headers, body = await self._get(ip, "/status", STATUS_TIMEOUT_S)
            if code != 200:
                await self._mark_offline(f"/status returned HTTP {code}")
                return
            status = json.loads(body)
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as exc:
            # Keep the address for a while: a board that was just unplugged is still at the
            # same address as far as the network is concerned, and failing fast against it is
            # what makes the dashboard show OFFLINE promptly. Only give up on the address once
            # the failures have piled up, which is the case where the node genuinely moved
            # (a new lease from the hotspot) and a fresh lookup is the only way back.
            if self.live.consecutive_errors >= RERESOLVE_AFTER_FAILURES:
                self._resolver.forget(host)
            await self._mark_offline(f"{type(exc).__name__}: {exc}")
            return

        await self._mark_online()

        # --- block 2: making sense of the answer. Failure here is OURS, not the node's. ---
        try:
            await self._apply_status(status)
            await self._events.node_status(self.live)
        except Exception:  # noqa: BLE001
            # Deliberately broad and deliberately non-fatal. The node answered; a defect in
            # our own handling must not be reported as dead hardware.
            log.exception("node %s: failed to process status (node stays online)", node_id)

        # --- block 3: the frame, only when there is one to fetch. ---
        if not self.live.cam_on:
            return
        try:
            code, _headers, jpeg = await self._get(ip, "/shot.jpg", FRAME_TIMEOUT_S)
            if code == 200 and jpeg[:2] == b"\xff\xd8":
                # Correct orientation here, once, so everything downstream - recognition and
                # every dashboard tile alike - works from an upright frame. See frames.py.
                # Off the event loop: imdecode/rotate/imencode are CPU-bound, and this loop is
                # shared by all six nodes' pollers plus every HTTP response (the dashboard's
                # own tile fetches included) - blocking it here delays all of them, not just
                # this node's own next tick.
                loop = asyncio.get_running_loop()
                jpeg = await loop.run_in_executor(None, rotate_jpeg, jpeg, self.live.rotation_deg)
                self.live.last_frame = jpeg
                self.live.last_frame_at = time.monotonic()
                await self._events.frame(self.live, jpeg)
            elif code != 503:
                # 503 is the node telling us the camera is still warming: expected, not an error.
                log.debug("node %s: /shot.jpg returned HTTP %d", node_id, code)
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            # A frame we could not fetch is not a node we cannot reach: /status just answered.
            # Keep the last good frame and try again next tick.
            log.debug("node %s: frame fetch failed (%s), keeping last frame", node_id, exc)
        except Exception:  # noqa: BLE001
            # Anything from OUR side of the frame - recognition, gate/zone logic, a database
            # write - is a bug in this program, not a dead node. Letting it escape reached the
            # supervisor, which restarts the task after 2s; for a deterministic fault (one bad
            # row in `people`, say) that is an endless restart loop and the node never polls
            # again. Same split as block 2: the node stays online, we log and carry on.
            log.exception("node %s: frame processing failed (node stays online)", node_id)

    async def run(self) -> None:
        """Poll forever at a steady cadence, correcting for how long each pass took."""
        while True:
            started = time.monotonic()
            await self.poll_once()
            # A node that has gone quiet without erroring (answered once, then nothing) still
            # has to time out.
            if self.live.online and self.live.age_s() > OFFLINE_AFTER_S:
                await self._mark_offline(f"no answer for {self.live.age_s():.0f}s")
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.0, STATUS_INTERVAL_S - elapsed))


async def supervise(
    poller: NodePoller,
    on_crash: Callable[[NodeLive, BaseException], Awaitable[None]] | None = None,
) -> None:
    """Keep one poller alive no matter what it does.

    A task that raises is restarted after a short pause, and the crash is reported so it
    lands in the audit log rather than only in a console nobody is reading during a shoot.
    Cancellation is passed through untouched, since that is a shutdown, not a fault.
    """
    while True:
        try:
            await poller.run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            poller.live.restarts += 1
            log.exception("poller for %s crashed (restart #%d), restarting in %.0fs",
                          poller.live.node_id, poller.live.restarts, SUPERVISOR_BACKOFF_S)
            if on_crash is not None:
                try:
                    await on_crash(poller.live, exc)
                except Exception:  # noqa: BLE001
                    log.exception("on_crash handler itself failed for %s", poller.live.node_id)
            await asyncio.sleep(SUPERVISOR_BACKOFF_S)
