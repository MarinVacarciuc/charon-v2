"""Wires the poller's Events protocol to everything that actually has to happen: recognition,
gate/zone decisions, the resulting database writes, the audit log, and the SSE hub.

Node health (online/offline) is simple and audited directly here. Frame and passage handling
delegate to the pure logic in recognition/gate.py and recognition/zones.py - this class's job
is only to supply them with facts (detected faces, policy lookups) and act on what they
decide (presence flips, zone moves, alerts). Keeping the decision logic pure and this class
as the only place touching the database is what let gate.py and zones.py ship with 24 unit
tests and no camera.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

import cv2
import numpy as np

from ..db.database import Database, utcnow
from ..db.repositories import audit, config, people, presence
from ..push import events as ev
from ..alerts.telegram import Telegram
from ..alerts.voice import VoicePlayer
from ..push.hub import SseHub
from ..recognition import gate, policy, zones
from ..recognition.engine import RecognitionEngine, is_confident_match
from ..recognition.observation import FaceObservation
from .state import NodeLive

log = logging.getLogger(__name__)


def _decode(jpeg: bytes) -> np.ndarray | None:
    return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)


def _now() -> dt.datetime:
    # LOCAL time, not UTC. Hours windows are typed by a person who means local time, so that
    # is the clock the decision has to be made against - see policy.policy_now(). Storage
    # stays UTC everywhere; only the comparison is local.
    return policy.policy_now()


class BrainEvents:
    def __init__(self, db: Database, hub: SseHub, engine: RecognitionEngine,
                 voice: VoicePlayer | None = None, telegram: Telegram | None = None) -> None:
        self._db = db
        self._hub = hub
        self._engine = engine
        self._voice = voice
        self._tg = telegram
        self._gate_states: dict[str, gate.GateNodeState] = {}
        self._zone_states: dict[str, zones.ZoneNodeState] = {}
        # Last frame's face-count per node, for the tailgating check at passage time - a
        # passage is reported from /status independent of frame timing, so this is the
        # freshest count available rather than a fresh detect() on every passage tick.
        self._last_face_count: dict[str, int] = {}

    def reset_live_state(self) -> None:
        """Drop every per-node tracker and pending decision - called by the take reset.
        Without this, a committed identity or a pending decision from the previous take
        survives into the next one and the first passage of a new take could bind to
        someone who is no longer even in frame."""
        self._gate_states.clear()
        self._zone_states.clear()
        self._last_face_count.clear()

    async def _voice_on(self) -> bool:
        return await config.get_bool(self._db, "voice_enabled", True)

    async def _tg_on(self) -> bool:
        return await config.get_bool(self._db, "telegram_enabled", True)

    # ------------------------------------------------------------------ node health

    async def node_online(self, node: NodeLive) -> None:
        await audit.record(self._db, "node_online", f"{node.node_id} online",
                           severity="info", node_id=node.node_id)
        await self._hub.publish(ev.node_status(node.node_id, online=True, cam_on=node.cam_on))

    async def node_offline(self, node: NodeLive, reason: str) -> None:
        await audit.record(self._db, "node_offline", f"{node.node_id} offline: {reason}",
                           severity="alert", node_id=node.node_id, details={"reason": reason})
        await self._hub.publish(ev.node_status(node.node_id, online=False, cam_on=False, reason=reason))

    async def node_status(self, node: NodeLive) -> None:
        pass  # 3 Hz x six nodes would flood both audit and SSE; /nodes serves live values instead

    # ------------------------------------------------------------------ recognition

    async def _observe_faces(self, frame: np.ndarray) -> list[tuple[FaceObservation, np.ndarray]]:
        """Every face this frame, largest first, each paired with its raw detection row (the
        row is needed by nothing downstream yet, but keeping it available avoids re-detecting
        if a future caller needs the box/landmarks).

        detect()/embed() are OpenCV DNN forward passes - CPU-bound, measured at ~12 ms and
        ~6 ms each on this hardware - and this ran on the bare event loop until 2026-09-08.
        That loop is shared by all six nodes' pollers and every HTTP response, dashboard tiles
        included, so ~20 ms of blocking work per face, per frame, per camera-on node was
        delaying all of them, not just this node's own next tick. Both now run in the default
        executor.
        """
        loop = asyncio.get_running_loop()
        rows = await loop.run_in_executor(None, self._engine.detect, frame)
        if rows.shape[0] == 0:
            return []
        threshold = await config.get_float(self._db, "sim_threshold", 0.45)
        margin_cfg = await config.get_float(self._db, "sim_margin", 0.05)

        pairs: list[tuple[FaceObservation, np.ndarray]] = []
        for row in rows:
            vec = await loop.run_in_executor(None, self._engine.embed, frame, row)
            c = self._engine.recognise(vec)  # plain numpy dot products over a small roster -
            confident = is_confident_match(c, threshold=threshold, margin=margin_cfg)  # cheap enough to stay on the loop
            area = float(row[2]) * float(row[3])
            pairs.append((FaceObservation(person_id=c.person_id if confident else None,
                                          confident=confident, area=area), row))
        pairs.sort(key=lambda pr: pr[0].area, reverse=True)
        return pairs

    async def frame(self, node: NodeLive, jpeg: bytes) -> None:
        loop = asyncio.get_running_loop()
        frame = await loop.run_in_executor(None, _decode, jpeg)
        if frame is None:
            return
        pairs = await self._observe_faces(frame)
        faces = [p[0] for p in pairs]
        self._last_face_count[node.node_id] = len(faces)

        if node.is_gate:
            await self._process_gate_frame(node, faces)
        elif node.role == "zone" and node.zone:
            await self._process_zone_frame(node, faces)

    async def passage(self, node: NodeLive, count: int) -> None:
        if not node.is_gate or node.direction is None:
            return
        state = self._gate_states.setdefault(node.node_id, gate.GateNodeState())
        # Only the COUNT matters to gate.process_passage's tailgating check; real
        # FaceObservation instances just keep the call honestly typed rather than passing a
        # bare int where the signature expects the real shape.
        faces_now = [FaceObservation(None, False)] * self._last_face_count.get(node.node_id, 0)
        now = _now()
        bind_window = await config.get_float(self._db, "gate_bind_window_s", 3.0)
        events = gate.process_passage(state, node.node_id, node.direction, faces_now, now,
                                      bind_window_s=bind_window)
        for e in events:
            await self._apply_gate_event(node, e)

    # ------------------------------------------------------------------ gate

    async def _policy_check_for(self, person_id: int):
        """Pre-fetch one person's policy facts and return a plain sync closure over them -
        gate.process_frame calls this synchronously, so the DB read has to happen before the
        call, not inside it. Only ever invoked with the frame's own primary candidate, so
        fetching just that one person is always sufficient."""
        person = await people.load_policy_person(self._db, person_id)

        def check(pid: int, now):
            if person is None:
                return False, "NOT ENROLLED"
            return policy.policy_ok(person, now)

        return check

    async def _process_gate_frame(self, node: NodeLive, faces: list[FaceObservation]) -> None:
        state = self._gate_states.setdefault(node.node_id, gate.GateNodeState())
        # Applied per frame rather than only at construction, so changing it in Settings takes
        # effect on a running system instead of at the next restart.
        state.tracker.set_confirm_frames(await config.get_int(self._db, "confirm_frames", 3))
        now = _now()

        primary_id = faces[0].person_id if faces and faces[0].confident else None
        check = await self._policy_check_for(primary_id) if primary_id is not None else (lambda pid, now: (False, "UNKNOWN"))

        bind_window = await config.get_float(self._db, "gate_bind_window_s", 3.0)
        events = gate.process_frame(state, node.node_id, faces, check, now,
                                    bind_window_s=bind_window)
        for e in events:
            await self._apply_gate_event(node, e)

    async def _apply_gate_event(self, node: NodeLive, e: gate.GateEvent) -> None:
        if e.kind == "decision":
            p = await people.get_by_id(self._db, e.person_id) if e.person_id else None
            name = p["name"] if p else "unknown"
            await audit.record(
                self._db, "gate_decision", f"{node.node_id}: {name} -> {'GRANTED' if e.granted else 'DENIED ' + e.reason}",
                severity="info" if e.granted else "warn", node_id=node.node_id, person_id=e.person_id,
            )
            await self._hub.publish(ev.alert("gate_decision", f"{name}: {'granted' if e.granted else 'denied'}",
                                             node=node.node_id, person_id=e.person_id, granted=e.granted))
            # Beat 1: the spoken line lands on the DECISION, not on the passage, so the voice,
            # the green light and the phone all happen together as the person walks up.
            if self._voice and node.direction == "in" and await self._voice_on():
                if e.granted:
                    self._voice.welcome(name)
                else:
                    self._voice.denied()

        elif e.kind == "entry":
            token, was_already_in = await presence.commit_entry(self._db, e.person_id)
            p = await people.get_by_id(self._db, e.person_id)
            name = p["name"] if p else "unknown"
            await audit.record(self._db, "entry", f"{name} entered via {node.node_id} (token {token})",
                               node_id=node.node_id, person_id=e.person_id)
            await self._hub.publish(ev.passage(node.node_id, "in", 0))
            if self._tg and p and p.get("telegram_chat_id") and await self._tg_on():
                self._tg.entry_token(p["telegram_chat_id"], name, token)
            if was_already_in:
                await audit.record(self._db, "concurrent_entry", f"{name} entered while already on-site",
                                   severity="alert", node_id=node.node_id, person_id=e.person_id)
                await self._hub.publish(ev.alert("concurrent_entry", f"{name}: concurrent entry", node=node.node_id))

        elif e.kind == "exit":
            was_in = await presence.commit_exit(self._db, e.person_id)
            p = await people.get_by_id(self._db, e.person_id)
            name = p["name"] if p else "unknown"
            await audit.record(self._db, "exit", f"{name} exited via {node.node_id}, token annulled",
                               node_id=node.node_id, person_id=e.person_id)
            await self._hub.publish(ev.passage(node.node_id, "out", 0))
            if not was_in:
                await audit.record(self._db, "exit_without_entry", f"{name} exited without a recorded entry",
                                   severity="alert", node_id=node.node_id, person_id=e.person_id)
                await self._hub.publish(ev.alert("exit_without_entry", f"{name}: exit without entry", node=node.node_id))

        elif e.kind == "denied_crossed":
            token, _ = await presence.commit_entry(self._db, e.person_id)
            p = await people.get_by_id(self._db, e.person_id)
            name = p["name"] if p else "unknown"
            await audit.record(self._db, "denied_crossed",
                               f"{name} was denied ({e.reason}) but crossed {node.node_id} anyway",
                               severity="alert", node_id=node.node_id, person_id=e.person_id)
            await self._hub.publish(ev.alert("denied_crossed", f"{name}: denied but crossed", node=node.node_id))

        elif e.kind == "unidentified_passage":
            await audit.record(self._db, "unidentified_passage", f"unidentified passage at {node.node_id}",
                               severity="alert", node_id=node.node_id)
            await self._hub.publish(ev.alert("unidentified_passage", f"unidentified passage", node=node.node_id))

        elif e.kind == "tailgating":
            await audit.record(self._db, "tailgating", f"possible tailgating at {node.node_id} ({e.face_count} faces)",
                               severity="alert", node_id=node.node_id)
            await self._hub.publish(ev.alert("tailgating", f"possible tailgating ({e.face_count} faces)", node=node.node_id))

    # ------------------------------------------------------------------ zones

    async def _zone_check_for(self, person_ids: set[int]):
        people_by_id = {}
        role_zones_by_role: dict[str, set[str]] = {}
        for pid in person_ids:
            p = await people.load_policy_person(self._db, pid)
            people_by_id[pid] = p
            if p is not None and p.role not in role_zones_by_role:
                role_zones_by_role[p.role] = await people.load_role_zones(self._db, p.role)

        def check(pid: int, zone_name: str, now):
            p = people_by_id.get(pid)
            if p is None:
                return False, "NOT ENROLLED"
            role_zones = role_zones_by_role.get(p.role, set())
            return policy.zone_allowed(p, role_zones, zone_name, now)

        return check

    async def _process_zone_frame(self, node: NodeLive, faces: list[FaceObservation]) -> None:
        state = self._zone_states.setdefault(node.node_id, zones.ZoneNodeState())
        now = _now()

        candidate_ids = {f.person_id for f in faces if f.confident and f.person_id is not None}
        check = await self._zone_check_for(candidate_ids) if candidate_ids else (lambda pid, z, now: (False, "UNKNOWN"))

        events = zones.process_frame(
            state, node.node_id, node.zone, faces, check, now,
            dwell_s=await config.get_float(self._db, "dwell_ms", 2000.0) / 1000.0,
            unknown_throttle_s=await config.get_float(self._db, "unknown_zone_throttle_s", 30.0),
            wrong_zone_throttle_s=await config.get_float(self._db, "wrong_zone_throttle_s", 60.0))
        for e in events:
            await self._apply_zone_event(node, e)

    async def _apply_zone_event(self, node: NodeLive, e: zones.ZoneEvent) -> None:
        if e.kind == "zone_update":
            p = await people.get_by_id(self._db, e.person_id)
            # Only people who are actually on site can be in a zone. Without this a camera
            # recognising someone through a window, or before they reach the gate, writes a
            # zone for an off-site person - which then survives their entry and shows them
            # in a room they never walked into.
            if not p or p.get("presence") != "in":
                return
            name = p["name"]
            await presence.set_zone(self._db, e.person_id, e.zone)
            await audit.record(self._db, "zone_update", f"{name} -> {e.zone}",
                               node_id=node.node_id, person_id=e.person_id)
            await self._hub.publish(ev.node_status(node.node_id, online=True, cam_on=node.cam_on,
                                                    zone_person=e.person_id, zone=e.zone))

        elif e.kind == "wrong_zone":
            p = await people.get_by_id(self._db, e.person_id)
            name = p["name"] if p else "unknown"
            await audit.record(self._db, "wrong_zone", f"{name} in {e.zone} ({e.reason})",
                               severity="alert", node_id=node.node_id, person_id=e.person_id)
            await self._hub.publish(ev.alert("wrong_zone", f"{name}: not allowed in {e.zone}",
                                             node=node.node_id, zone=e.zone))
            # Beat 5 is deliberately loud on all three surfaces at once: the board, the
            # person's own phone, and the room.
            if self._voice and await self._voice_on():
                self._voice.denied_zone(e.zone)
            if self._tg and p and p.get("telegram_chat_id") and await self._tg_on():
                self._tg.wrong_zone(p["telegram_chat_id"], name, e.zone, e.reason)

        elif e.kind == "unknown_in_zone":
            await audit.record(self._db, "unknown_in_zone", f"unknown person in {e.zone}",
                               severity="alert", node_id=node.node_id)
            await self._hub.publish(ev.alert("unknown_in_zone", f"unknown person in {e.zone}",
                                             node=node.node_id, zone=e.zone))
            if self._voice and await self._voice_on():
                self._voice.unknown_in_zone()
