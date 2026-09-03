"""Enrolment and the roster. Enrolment is the one place camera choice is not optional -
REBUILD_PROMPT §0.6.4: resolving "whichever camera has a face right now" at click time
already caused a real bug (a one-frame miss on the intended camera plus a stranger walking
past a different one could enrol the wrong person under someone else's name and access
rights). `node` is a required query parameter here for exactly that reason, not a default.
"""
from __future__ import annotations

import cv2
import numpy as np
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db.repositories import embeddings, people
from ..recognition.engine import is_confident_match

router = APIRouter(prefix="/people")


def _decode(jpeg: bytes) -> np.ndarray | None:
    frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    return frame


@router.get("")
async def list_people(request: Request):
    rows = await people.list_all(request.app.state.db)
    engine = request.app.state.engine
    return {"people": [
        {**{k: v for k, v in r.items() if k not in ("session_token",)},
         "samples": engine.sample_count(r["id"])}
        for r in rows
    ]}


@router.post("/enroll")
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


@router.delete("/{person_id}/samples")
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
