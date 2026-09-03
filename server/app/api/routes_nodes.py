"""Read-only node routes: frame, health, and the SSE stream.

Nothing here mutates anything, so nothing here needs the admin token (see docs/BUILD_PLAN.md
on the auth split: mutating routes require it, read-only routes stay open on the LAN so a
phone propped at the gate needs no login).
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ..push.events import keepalive
from ..push.hub import SseHub

log = logging.getLogger(__name__)

router = APIRouter()

KEEPALIVE_INTERVAL_S = 15.0


@router.get("/frame.jpg")
async def frame(request: Request, node: str):
    """Latest frame the poller has for this node.

    Served from the poller's cache rather than proxied live per-request: the node is already
    being polled continuously for the brain's own use, so every open browser tab reusing that
    same cached frame is what keeps six cameras from being asked for a frame once per viewer.
    """
    registry = request.app.state.registry
    live = registry.get(node)
    if live is None:
        return JSONResponse({"error": f"unknown node '{node}'"}, status_code=404)
    if live.last_frame is None:
        return JSONResponse(
            {"error": f"no frame yet from '{node}'", "online": live.online, "cam_on": live.cam_on},
            status_code=503,
        )
    return Response(content=live.last_frame, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store", "X-Frame-Age-Ms": str(int(live.frame_age_s() * 1000))})


@router.get("/nodes")
async def nodes(request: Request):
    """One JSON snapshot of every node's live state. What a dashboard's node strip renders."""
    registry = request.app.state.registry
    out = []
    for live in registry.all():
        out.append({
            "id": live.node_id,
            "role": live.role,
            "zone": live.zone,
            "rotation_deg": live.rotation_deg,
            "state": live.ui_state(),          # "live" | "armed" | "offline" - the three that must never be confused
            "online": live.online,
            "cam_on": live.cam_on,
            "near": live.near,
            "near_cm": live.near_cm,
            "pass_cm": live.pass_cm,
            "passages": live.passages,
            "age_s": None if live.age_s() == float("inf") else round(live.age_s(), 1),
            "restarts": live.restarts,
            "last_error": live.last_error,
        })
    return {"nodes": out}


@router.get("/events")
async def events(request: Request):
    """SSE stream. EventSource reconnects on its own, which is the whole reason this project
    uses SSE instead of a hand-rolled WebSocket reconnect (see docs/BUILD_PLAN.md)."""
    hub: SseHub = request.app.state.hub
    queue = hub.subscribe()

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_INTERVAL_S)
                except asyncio.TimeoutError:
                    event = keepalive()
                yield hub.format_sse(event)
        finally:
            hub.unsubscribe(queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/nodes/{node_id}/rotation")
async def set_rotation(request: Request, node_id: str, deg: int):
    """Set one node's frame rotation. Per node, never global - six cameras get mounted six
    ways (REBUILD_PROMPT §0.6.9). Written to the database so it survives a restart, and
    applied to the live node immediately so the next frame is already correct.

    Mutating, so it gets the admin token when Day 8 wires auth across every mutating route.
    """
    if deg not in (0, 90, 180, 270):
        return JSONResponse({"error": f"rotation must be 0, 90, 180 or 270, got {deg}"}, status_code=400)
    live = request.app.state.registry.get(node_id)
    if live is None:
        return JSONResponse({"error": f"unknown node '{node_id}'"}, status_code=404)

    await request.app.state.db.execute(
        "UPDATE nodes SET rotation_deg = ? WHERE id = ?", (deg, node_id))
    live.rotation_deg = deg
    # Drop the cached frame: it is in the OLD orientation, and serving it once more would
    # look like the setting had not taken.
    live.last_frame = None
    return {"node": node_id, "rotation_deg": deg}
