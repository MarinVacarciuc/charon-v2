"""Hostname resolution for the nodes, forced to IPv4 and cached.

This exists because of one measured, expensive bug. macOS resolves `*.local` with
AF_UNSPEC, asking for both A and AAAA records. The ESP32's mDNS responder answers the A
half and simply never answers the AAAA half, so the resolver waits out the full IPv6
timeout on every single lookup before falling back to IPv4.

Measured on this hardware: 5.002 s with AF_UNSPEC against 0.010 s with AF_INET. At a few
polls a second across six nodes that is not a slow path, it is a total stall - and it
presents as healthy boards reading OFFLINE, which sends you looking at the wrong thing.

So: ask for AF_INET explicitly, cache the answer, and connect to the literal IP. Connecting
by IP also means aiohttp's own resolver never runs at all.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)

DEFAULT_TTL_S = 60.0


@dataclass
class _Entry:
    ip: str
    at: float


class Ipv4Resolver:
    def __init__(self, ttl_s: float = DEFAULT_TTL_S) -> None:
        self._ttl = ttl_s
        self._cache: dict[str, _Entry] = {}

    async def resolve(self, host: str) -> str | None:
        """Return an IPv4 address for `host`, or None if it cannot be resolved.

        Returning None rather than raising is deliberate: a node that is simply switched off
        is a normal, expected state, not an exception. The caller marks it offline and moves
        on to the other five.
        """
        # Already an address: nothing to look up, and no cache entry to keep.
        try:
            socket.inet_aton(host)
            return host
        except OSError:
            pass

        hit = self._cache.get(host)
        now = time.monotonic()
        if hit is not None and now - hit.at < self._ttl:
            return hit.ip

        loop = asyncio.get_running_loop()
        try:
            # getaddrinfo already runs in the default executor, so the event loop is not
            # blocked; family=AF_INET is the entire fix.
            infos = await loop.getaddrinfo(
                host, None, family=socket.AF_INET, type=socket.SOCK_STREAM
            )
        except (OSError, socket.gaierror) as exc:
            log.debug("resolve %s failed: %s", host, exc)
            return None

        if not infos:
            return None
        ip = infos[0][4][0]
        self._cache[host] = _Entry(ip=ip, at=now)
        return ip

    def forget(self, host: str) -> None:
        """Drop a cached address.

        Called when a request to that address fails, so a node that moved (the hotspot handed
        out a different lease) is picked up on the next attempt instead of being retried at a
        stale address until the TTL happens to expire.
        """
        self._cache.pop(host, None)

    def cached(self) -> dict[str, str]:
        return {h: e.ip for h, e in self._cache.items()}
