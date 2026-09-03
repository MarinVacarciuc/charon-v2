"""Event shapes pushed over SSE.

Kept as plain dicts with a `type` field rather than a class hierarchy: every consumer (the
dashboard's JS, curl during development, the report's "here is the event stream" evidence)
just wants readable JSON, and pydantic validation on the way out would only protect against
bugs already caught by mypy/tests on the way in.
"""
from __future__ import annotations

from typing import Any

from ..db.database import utcnow


def node_status(node_id: str, online: bool, cam_on: bool, **extra: Any) -> dict:
    return {"type": "node_status", "ts": utcnow(), "node": node_id, "online": online, "cam_on": cam_on, **extra}


def passage(node_id: str, direction: str | None, count: int) -> dict:
    return {"type": "passage", "ts": utcnow(), "node": node_id, "direction": direction, "count": count}


def alert(kind: str, message: str, **extra: Any) -> dict:
    return {"type": "alert", "ts": utcnow(), "kind": kind, "message": message, **extra}


def keepalive() -> dict:
    return {"type": "keepalive", "ts": utcnow()}
