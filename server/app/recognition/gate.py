"""Gate decision and passage-binding logic. Pure: given facts, produces events; no I/O.

This is the model Marin locked in over DEMO_ARCHITECTURE's original camera-only proposal,
2026-09-02: recognition names someone and issues a decision (BEAT 1 - green/red, voice,
token; see PendingDecision), but presence only flips when the PASS ultrasonic's counter
actually increments (BEAT 2 - a real body crossed the lane). A decision nobody ever walked
on is just someone who paused and left; a passage nobody decided about is a real anomaly.

Two events the old build never had at all, both real anomalies worth their own alert:
DENIED_CROSSED (recognised, refused, walked through anyway) and UNIDENTIFIED_PASSAGE (a body
crossed with no fresh decision to bind it to - the old build only ever logged this at ENTER
and stayed silent about it at EXIT).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .observation import FaceObservation
from .tracker import IdentityTracker

BIND_WINDOW_S = 3.0  # a decision older than this cannot be claimed by a later passage


@dataclass
class PendingDecision:
    person_id: int | None
    granted: bool
    reason: str
    decided_at: datetime
    face_count: int


@dataclass
class GateNodeState:
    """Everything gate logic remembers between frames and passages for one node."""

    tracker: IdentityTracker = field(default_factory=IdentityTracker)
    pending: PendingDecision | None = None
    _last_committed: int | None = None


@dataclass(frozen=True)
class GateEvent:
    kind: str  # decision | entry | exit | unidentified_passage | denied_crossed | tailgating
    node_id: str
    person_id: int | None = None
    granted: bool | None = None
    reason: str = ""
    face_count: int = 1


def process_frame(state: GateNodeState, node_id: str, faces: list[FaceObservation],
                  policy_check, now: datetime) -> list[GateEvent]:
    """One frame -> zero or one `decision` event.

    `faces` should be pre-sorted largest first; only faces[0] drives the decision (a gate has
    one expected subject at a time), the rest only matter at passage time for tailgating.
    `policy_check(person_id, now) -> (granted: bool, reason: str)` is policy.policy_ok,
    injected so this module never needs a real Person object to be tested.
    """
    if not faces:
        state.tracker.observe(None)
        return []

    primary = faces[0]
    raw_id = primary.person_id if primary.confident else None
    committed = state.tracker.observe(raw_id)

    if committed == state._last_committed:
        if committed is not None and state.pending is not None:
            # Same person, still confidently seen: keep the binding window fresh so a passage
            # a few seconds later is not treated as stale just because nothing NEW happened
            # this frame - REBUILD_PROMPT's lesson about only ever re-deriving from
            # unconditionally-available state applies here too: decided_at always reflects
            # the most recent frame that reaffirmed this identity, not the first one.
            state.pending.decided_at = now
        return []

    state._last_committed = committed
    if committed is None:
        state.pending = None
        return []

    granted, reason = policy_check(committed, now)
    state.pending = PendingDecision(person_id=committed, granted=granted, reason=reason,
                                    decided_at=now, face_count=len(faces))
    return [GateEvent(kind="decision", node_id=node_id, person_id=committed,
                      granted=granted, reason=reason, face_count=len(faces))]


def process_passage(state: GateNodeState, node_id: str, direction: str,
                    faces_now: list[FaceObservation], now: datetime) -> list[GateEvent]:
    """A real, sensor-confirmed body crossing the lane - direction is "in" or "out", already
    resolved from which physical node's counter moved (never a global mode toggle)."""
    events: list[GateEvent] = []

    if len(faces_now) > 1:
        events.append(GateEvent(kind="tailgating", node_id=node_id, face_count=len(faces_now)))

    pending = state.pending
    fresh = pending is not None and (now - pending.decided_at) <= timedelta(seconds=BIND_WINDOW_S)

    if not fresh:
        events.append(GateEvent(kind="unidentified_passage", node_id=node_id))
        return events

    if direction == "in" and not pending.granted:
        # Recognised and refused, but the body crossed anyway. The old build had no event for
        # this at all - a denied entry just sat un-audited past the initial refusal.
        events.append(GateEvent(kind="denied_crossed", node_id=node_id, person_id=pending.person_id,
                                reason=pending.reason))
        return events

    # Exit is fail-safe by design: no policy gate on the way out, ever - only whether we know
    # who is leaving. If direction is "out", granted/denied does not apply.
    kind = "entry" if direction == "in" else "exit"
    events.append(GateEvent(kind=kind, node_id=node_id, person_id=pending.person_id))
    state.pending = None  # consumed - a second passage needs its own fresh decision
    return events
