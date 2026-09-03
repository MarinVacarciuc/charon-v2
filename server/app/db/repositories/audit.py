"""One place that knows the audit_log column list, so it cannot drift between call sites.

Every part of the brain that raises a security-relevant event - a node going dark, a gate
decision, a zone violation, an overstay - goes through this. `SELECT ts, message ORDER BY ts`
against the resulting table reproduces the old flat text log for the report, but with
severity and the foreign keys it is actually queryable.
"""
from __future__ import annotations

import json
import logging

from ..database import Database, utcnow

log = logging.getLogger(__name__)


async def record(
    db: Database,
    event_type: str,
    message: str,
    *,
    severity: str = "info",
    actor: str = "system",
    node_id: str | None = None,
    person_id: int | None = None,
    zone_id: int | None = None,
    details: dict | None = None,
) -> None:
    try:
        await db.execute(
            """
            INSERT INTO audit_log (ts, actor, event_type, severity, node_id, person_id, zone_id,
                                    message, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (utcnow(), actor, event_type, severity, node_id, person_id, zone_id, message,
             json.dumps(details or {})),
        )
    except Exception:  # noqa: BLE001
        # An audit-logging failure must never take down whatever real event triggered it - the
        # event itself (a node going offline, a gate decision) still has to proceed.
        log.exception("failed to write audit_log row: %s / %s", event_type, message)


async def recent(db: Database, limit: int = 40) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT ts, severity, event_type, node_id, message FROM audit_log ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in rows]
