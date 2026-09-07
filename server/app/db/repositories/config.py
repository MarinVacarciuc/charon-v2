"""Runtime tuning values, cached briefly.

These live in the database so they survive a restart, but they are read on paths that run
several times a second per node - the recognition thresholds were being fetched with a fresh
query on every single frame, roughly eighteen queries a second for values that change perhaps
once a week.

A short TTL is the right shape rather than caching forever: an operator changing a setting in
the yard needs it to take effect while they are still standing there, and two seconds is well
inside "did that do anything?" A cache that only refreshed on restart would recreate exactly
the problem config_kv exists to avoid.
"""
from __future__ import annotations

import time

from ..database import Database

TTL_S = 2.0

_cache: dict[str, str] = {}
_fetched_at = 0.0


async def all_values(db: Database) -> dict[str, str]:
    global _cache, _fetched_at
    now = time.monotonic()
    if _cache and (now - _fetched_at) < TTL_S:
        return _cache
    rows = await db.fetch_all("SELECT key, value FROM config_kv")
    _cache = {r["key"]: r["value"] for r in rows}
    _fetched_at = now
    return _cache


def invalidate() -> None:
    """Called after a write so the change is visible immediately rather than up to TTL late."""
    global _fetched_at
    _fetched_at = 0.0


async def get_float(db: Database, key: str, default: float) -> float:
    try:
        return float((await all_values(db))[key])
    except (KeyError, TypeError, ValueError):
        return default


async def get_int(db: Database, key: str, default: int) -> int:
    try:
        return int(float((await all_values(db))[key]))
    except (KeyError, TypeError, ValueError):
        return default


async def get_bool(db: Database, key: str, default: bool) -> bool:
    v = (await all_values(db)).get(key)
    if v is None:
        return default
    return v.strip() in ("1", "true", "True", "yes", "on")
