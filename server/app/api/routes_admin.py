"""Audit access and the take-reset control."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..db.database import utcnow
from ..db.repositories import audit
from .auth import require_admin

router = APIRouter()


@router.get("/audit")
async def get_audit(request: Request, limit: int = 100):
    rows = await audit.recent(request.app.state.db, limit=limit)
    return {"entries": rows}


@router.post("/reset", dependencies=[Depends(require_admin)])
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


@router.get("/config")
async def get_config(request: Request):
    rows = await request.app.state.db.fetch_all("SELECT key, value FROM config_kv ORDER BY key")
    return {"config": {r["key"]: r["value"] for r in rows}}


@router.post("/config", dependencies=[Depends(require_admin)])
async def set_config(request: Request):
    """Update tuning values. They live in config_kv rather than in a file or in memory because
    anything that changes how strict the system is has to survive a restart - an in-memory
    mode flag that silently reverts is exactly the failure REBUILD_PROMPT §0.6.6 describes."""
    body = await request.json()
    db = request.app.state.db
    known = {r["key"] for r in await db.fetch_all("SELECT key FROM config_kv")}
    changed = {}
    for key, value in (body or {}).items():
        if key not in known:
            continue  # refuse to invent settings that nothing reads
        await db.execute("UPDATE config_kv SET value = ?, updated_at = ? WHERE key = ?",
                         (str(value), utcnow(), key))
        changed[key] = str(value)
    if changed:
        await audit.record(db, "config_change", ", ".join(f"{k}={v}" for k, v in changed.items()),
                           actor="admin")
    return {"ok": True, "changed": changed}
