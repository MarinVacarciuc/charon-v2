"""Audit access and the take-reset control.

No admin token enforced yet - Day 8 wires that in for every mutating route at once, per
docs/BUILD_PLAN.md's decision to build A7 auth as one pass rather than bolt it onto each
route as it's written. Noted here so it is not mistaken for an oversight.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..db.database import utcnow
from ..db.repositories import audit

router = APIRouter()


@router.get("/audit")
async def get_audit(request: Request, limit: int = 100):
    rows = await audit.recent(request.app.state.db, limit=limit)
    return {"entries": rows}


@router.post("/reset")
async def reset_take(request: Request):
    """Clear live state for a fresh take: everyone off-site, no zone, no token, no in-memory
    gate/zone tracking left over from the previous take. Deliberately does NOT touch
    audit_log - the point is a clean board for filming, not losing the record of what
    happened. The reset itself is one audited line, so a re-shoot boundary is visible in the
    permanent trail rather than erasing everything before it."""
    db = request.app.state.db
    await db.execute(
        "UPDATE people SET presence='out', session_token='', at_zone_id=NULL, entry_time='', updated_at=?",
        (utcnow(),),
    )
    request.app.state.events.reset_live_state()
    await audit.record(db, "reset_take", "board reset for a new take", actor="operator")
    await request.app.state.hub.publish({"type": "reset", "ts": utcnow()})
    return {"ok": True}
