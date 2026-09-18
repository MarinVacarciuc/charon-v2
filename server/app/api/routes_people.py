"""Enrolment and the roster. Enrolment is the one place camera choice is not optional -
REBUILD_PROMPT §0.6.4: resolving "whichever camera has a face right now" at click time
already caused a real bug (a one-frame miss on the intended camera plus a stranger walking
past a different one could enrol the wrong person under someone else's name and access
rights). `node` is a required query parameter here for exactly that reason, not a default.
"""
from __future__ import annotations

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import JSONResponse

from ..db.repositories import audit, embeddings, people, presence
from .auth import require_admin
from ..recognition.engine import is_confident_match

router = APIRouter(prefix="/people")


def _decode(jpeg: bytes) -> np.ndarray | None:
    frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    return frame


@router.get("")
async def list_people(request: Request):
    rows = await people.list_all(request.app.state.db)
    engine = request.app.state.engine
    # The token itself never leaves the server: this page is designed to sit on a wall. Whether
    # one exists is all an operator needs to decide if there is anything to revoke.
    return {"people": [
        {**{k: v for k, v in r.items() if k not in ("session_token",)},
         "has_token": bool(r["session_token"]),
         "samples": engine.sample_count(r["id"])}
        for r in rows
    ]}


@router.post("/enroll", dependencies=[Depends(require_admin)])
async def enroll(request: Request, name: str, role: str, node: str):
    """Capture one sample from the named node's current frame and attach it to `name`,
    creating the person if they do not already exist. A repeat call for the same name adds
    another sample - REBUILD_PROMPT §10's "several angles and lightings" is the normal way
    to build up a roster entry, not an error.
    """
    db = request.app.state.db
    engine = request.app.state.engine
    registry = request.app.state.registry

    live = registry.get(node)
    if live is None:
        return JSONResponse({"error": f"unknown node '{node}'"}, status_code=404)
    if live.last_frame is None:
        return JSONResponse(
            {"error": f"no frame available from '{node}' yet", "online": live.online, "cam_on": live.cam_on},
            status_code=503,
        )

    frame = _decode(live.last_frame)
    if frame is None:
        return JSONResponse({"error": f"could not decode the current frame from '{node}'"}, status_code=500)

    faces = engine.detect(frame)
    if faces.shape[0] == 0:
        return JSONResponse({"error": f"no face detected in the current frame from '{node}'"}, status_code=422)
    if faces.shape[0] > 1:
        # Refuse rather than guess. Enrolling under an ambiguous frame is the same class of
        # mistake §0.6.4 warns about, just with two people in one shot instead of two cameras.
        return JSONResponse(
            {"error": f"{faces.shape[0]} faces detected in frame from '{node}' - "
                      "make sure only the person being enrolled is in view"},
            status_code=422,
        )

    vec = engine.embed(frame, faces[0])

    try:
        person_id = await people.get_or_create(db, name, role)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    await embeddings.add(db, person_id, vec, source="live", node_id=node)
    engine.add_sample(person_id, vec)  # visible to recognise() on the very next frame, no restart needed

    return {"person_id": person_id, "name": name, "node": node,
            "samples": engine.sample_count(person_id),
            "face_score": float(faces[0][14])}


MAX_PHOTO_BYTES = 12 * 1024 * 1024


@router.post("/enroll/photo", dependencies=[Depends(require_admin)])
async def enroll_photo(request: Request, name: str, role: str, photo: UploadFile = File(...)):
    """Same enrolment, from a file on the operator's machine instead of a camera frame.

    Worth having for a reason beyond convenience: a new starter can be on the roster before
    they first walk through the gate, and someone photographed under decent lighting gives a
    better template than a corridor camera at an angle. The face rules stay identical to live
    enrolment, including the refusal on more than one face, because an ambiguous group photo
    is the same mistake as an ambiguous frame and the source of the pixels does not change
    that. The row is stamped source='photo', so a later audit can tell which templates came
    from a controlled capture and which from the estate's own cameras.
    """
    db = request.app.state.db
    engine = request.app.state.engine

    blob = await photo.read()
    if not blob:
        return JSONResponse({"error": "the uploaded file is empty"}, status_code=400)
    if len(blob) > MAX_PHOTO_BYTES:
        return JSONResponse({"error": f"photo is larger than {MAX_PHOTO_BYTES // (1024 * 1024)} MB"},
                            status_code=413)

    # Decoded by content, not by filename or the browser's declared type: neither is evidence
    # of what the bytes actually are, and imdecode returning None is the honest test.
    frame = _decode(blob)
    if frame is None:
        return JSONResponse({"error": f"'{photo.filename}' is not an image this build can read "
                                      "(JPEG and PNG are the safe choices)"}, status_code=415)

    faces = engine.detect(frame)
    if faces.shape[0] == 0:
        return JSONResponse({"error": f"no face detected in '{photo.filename}'"}, status_code=422)
    if faces.shape[0] > 1:
        return JSONResponse(
            {"error": f"{faces.shape[0]} faces detected in '{photo.filename}' - "
                      "crop it so only the person being enrolled is in the picture"},
            status_code=422,
        )

    vec = engine.embed(frame, faces[0])

    try:
        person_id = await people.get_or_create(db, name, role)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    await embeddings.add(db, person_id, vec, source="photo")
    engine.add_sample(person_id, vec)
    await audit.record(db, "enrol_photo", f"{name}: template added from file '{photo.filename}'",
                       actor="admin", person_id=person_id)

    return {"person_id": person_id, "name": name, "source": "photo",
            "filename": photo.filename,
            "samples": engine.sample_count(person_id),
            "face_score": float(faces[0][14])}


@router.delete("/{person_id}/samples", dependencies=[Depends(require_admin)])
async def clear_samples(request: Request, person_id: int):
    """Wipe a person's face templates without deleting their record - the recovery path for
    a bad enrolment session, ported from the old build's /reface."""
    db = request.app.state.db
    n = await db.execute("DELETE FROM face_embeddings WHERE person_id = ?", (person_id,))
    engine = request.app.state.engine
    roster = await embeddings.load_all(db)
    engine.load_samples(roster)
    return {"person_id": person_id, "samples_now": engine.sample_count(person_id)}


@router.get("/recognise")
async def recognise_debug(request: Request, node: str):
    """Tuning readout: every face in the node's current frame, its best-candidate match, raw
    score and margin - independent of the confirm-frames gate, which needs a live sequence of
    frames rather than one snapshot. Mirrors the old build's on-screen "name score" overlay,
    as plain JSON instead of pixels burned into the frame."""
    engine = request.app.state.engine
    live = request.app.state.registry.get(node)
    if live is None:
        return JSONResponse({"error": f"unknown node '{node}'"}, status_code=404)
    if live.last_frame is None:
        return JSONResponse({"error": f"no frame available from '{node}' yet"}, status_code=503)

    frame = _decode(live.last_frame)
    faces = engine.detect(frame)
    settings = await request.app.state.db.fetch_one(
        "SELECT value FROM config_kv WHERE key='sim_threshold'"
    )
    margin_row = await request.app.state.db.fetch_one(
        "SELECT value FROM config_kv WHERE key='sim_margin'"
    )
    threshold = float(settings["value"]) if settings else 0.45
    margin_cfg = float(margin_row["value"]) if margin_row else 0.05

    out = []
    for row in faces:
        vec = engine.embed(frame, row)
        c = engine.recognise(vec)
        name = None
        if c.person_id is not None:
            p = await people.get_by_id(request.app.state.db, c.person_id)
            name = p["name"] if p else None
        out.append({
            "box": [float(x) for x in row[:4]],
            "detection_score": float(row[14]),
            "candidate_person_id": c.person_id,
            "candidate_name": name,
            "score": round(c.score, 4),
            "margin": round(c.margin, 4),
            "confident": is_confident_match(c, threshold=threshold, margin=margin_cfg),
        })
    return {"node": node, "faces": out, "enrolled_people": engine.enrolled_people}


@router.get("/roster")
async def roster(request: Request):
    """The roster as the staff page needs it: role, effective access, live JIT grants and
    sample count in one call, so the page never has to join anything client-side."""
    db = request.app.state.db
    engine = request.app.state.engine
    rows = await people.list_all(db)
    zones = [r["name"] for r in await db.fetch_all("SELECT name FROM zones ORDER BY sort_order")]
    roles = [r["name"] for r in await db.fetch_all("SELECT name FROM roles ORDER BY id")]

    out = []
    for r in rows:
        overrides = await db.fetch_all(
            "SELECT z.name FROM person_zone_overrides o JOIN zones z ON z.id = o.zone_id "
            "WHERE o.person_id = ?", (r["id"],))
        role_zones = await people.load_role_zones(db, r["role_name"])
        out.append({
            **{k: v for k, v in r.items() if k != "session_token"},
            "has_token": bool(r["session_token"]),
            "samples": engine.sample_count(r["id"]),
            "zone_overrides": [o["name"] for o in overrides],
            "role_zones": sorted(role_zones),
            "grants": await people.live_grants(db, r["id"]),
        })
    return {"people": out, "zones": zones, "roles": roles}


@router.post("/{person_id}", dependencies=[Depends(require_admin)])
async def update_person(request: Request, person_id: int):
    body = await request.json()
    db = request.app.state.db
    try:
        await people.update(db, person_id, body.get("fields", {}))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if "zone_overrides" in body:
        await people.set_zone_overrides(db, person_id, body["zone_overrides"])
    return {"ok": True, "person_id": person_id}


@router.delete("/{person_id}", dependencies=[Depends(require_admin)])
async def delete_person(request: Request, person_id: int):
    await people.delete(request.app.state.db, person_id)
    # Their embeddings cascaded with them; drop the in-memory copy too, or a deleted person
    # keeps being recognised until the next restart.
    roster = await embeddings.load_all(request.app.state.db)
    request.app.state.engine.load_samples(roster)
    return {"ok": True}


@router.post("/{person_id}/revoke-token", dependencies=[Depends(require_admin)])
async def revoke_token(request: Request, person_id: int):
    """Annul someone's live session token without moving them off site."""
    db = request.app.state.db
    p = await people.get_by_id(db, person_id)
    if p is None:
        return JSONResponse({"error": f"no person with id {person_id}"}, status_code=404)
    old = await presence.revoke_token(db, person_id)
    if not old:
        return {"ok": True, "revoked": False, "person_id": person_id}
    await audit.record(db, "token_revoked", f"{p['name']}: session token {old} revoked by an admin",
                       severity="warn", actor="admin", person_id=person_id)
    return {"ok": True, "revoked": True, "person_id": person_id}


@router.post("/{person_id}/grant", dependencies=[Depends(require_admin)])
async def grant(request: Request, person_id: int, zone: str, minutes: int = 15):
    """Just-in-time zone pass - DEMO_ARCHITECTURE calls this a headline beat, not an extra.
    It lapses on its own; there is no revert step for an admin to forget (threat model A4)."""
    if minutes < 1 or minutes > 24 * 60:
        return JSONResponse({"error": "minutes must be between 1 and 1440"}, status_code=400)
    db = request.app.state.db
    expires = await people.grant_zone(db, person_id, zone, minutes)
    p = await people.get_by_id(db, person_id)
    await audit.record(db, "grant", f"{p['name'] if p else person_id}: {zone} granted for {minutes} min "
                                    f"(until {expires})", actor="admin", person_id=person_id)
    return {"ok": True, "zone": zone, "expires_at": expires}


@router.delete("/{person_id}/grant", dependencies=[Depends(require_admin)])
async def ungrant(request: Request, person_id: int, zone: str | None = None):
    db = request.app.state.db
    await people.revoke_zone(db, person_id, zone)
    p = await people.get_by_id(db, person_id)
    await audit.record(db, "ungrant", f"{p['name'] if p else person_id}: "
                                      f"{zone or 'all temporary access'} revoked",
                       actor="admin", person_id=person_id)
    return {"ok": True}
