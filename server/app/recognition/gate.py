"""Gate decision logic. Pure: given facts, produces events; no I/O.

The two-beat model Marin locked in over DEMO_ARCHITECTURE's camera-only proposal on
2026-09-02 was: recognition names someone and issues a decision (BEAT 1 - green/red, voice,
token; see PendingDecision), but presence only flips when the PASS ultrasonic's counter
increments (BEAT 2 - a real body crossed the lane). Two anomalies fell out of the gap
between the beats, neither of which the old build had: DENIED_CROSSED (recognised, refused,
walked through anyway) and UNIDENTIFIED_PASSAGE (a body crossed with no decision to bind to).

BEAT 2 is switched off as of 2026-09-18, on Marin's call, because the sensor could not
deliver it. Measured in place: the PASS sonar idles BLOCKED against clutter sitting ~33 cm
in front of it (70% of samples inside its 60 cm threshold), and 21-34% of its samples are
noise excursions past the 80 cm hysteresis release, each of which fakes a clear-then-block
pair that is indistinguishable from a body. That counted 34 and 59 phantom crossings in
three minutes at the two gates, and any one of them landing inside the bind window after a
real recognition committed that person - which is exactly the symptom reported. Cross-talk
between six unsynchronised sonars on one bench feeds the same noise.

So process_frame now commits entry and exit itself and process_passage, below, is no longer
wired to anything. It is kept intact, and PendingDecision with it, because the sensor is
being abandoned for now rather than judged worthless - remounted facing a clear lane, with
a dwell-time guard instead of a bare edge, it would bring both anomaly events back. Nothing
calls it in the meantime, so re-wiring it means removing the direct commit here first, or
every crossing is counted twice.
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


def process_frame(state: GateNodeState, node_id: str, direction: str,
                  faces: list[FaceObservation], policy_check,
                  now: datetime) -> list[GateEvent]:
    """One frame -> a `decision`, and the entry or exit it now commits directly.

    `faces` should be pre-sorted largest first; only faces[0] drives the decision (a gate has
    one expected subject at a time), the rest only count towards tailgating.
    `policy_check(person_id, now) -> (granted: bool, reason: str)` is policy.policy_ok,
    injected so this module never needs a real Person object to be tested.

    The frame is the whole event here - see the module docstring for why the PASS sensor no
    longer gets a vote. The brain pulls frames only while the NEAR sonar reports someone
    inside one metre, so reaching this point already means "recognised, and standing at the
    gate". What it cannot mean is that they walked through: nothing measures that any more.
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
    events = [GateEvent(kind="decision", node_id=node_id, person_id=committed,
                        granted=granted, reason=reason, face_count=len(faces))]

    # Tailgating rides on the decision rather than on a passage, which also rate-limits it:
    # a decision only fires when the committed identity CHANGES, so a second face lingering
    # in frame raises one alert, not one per frame for as long as they stand there.
    if len(faces) > 1:
        events.append(GateEvent(kind="tailgating", node_id=node_id, face_count=len(faces)))

    # Exit is fail-safe by design: no policy gate on the way out, ever - only whether we know
    # who is leaving. Entry is the only direction a refusal can stop.
    if direction == "out":
        events.append(GateEvent(kind="exit", node_id=node_id, person_id=committed))
    elif granted:
        events.append(GateEvent(kind="entry", node_id=node_id, person_id=committed))
    return events


def process_passage(state: GateNodeState, node_id: str, direction: str,
                    faces_now: list[FaceObservation], now: datetime,
                    bind_window_s: float = BIND_WINDOW_S) -> list[GateEvent]:
    """A real, sensor-confirmed body crossing the lane - direction is "in" or "out", already
    resolved from which physical node's counter moved (never a global mode toggle)."""
    events: list[GateEvent] = []

    if len(faces_now) > 1:
        events.append(GateEvent(kind="tailgating", node_id=node_id, face_count=len(faces_now)))

    pending = state.pending
    fresh = pending is not None and (now - pending.decided_at) <= timedelta(seconds=bind_window_s)

    if not fresh:
        events.append(GateEvent(kind="unidentified_passage", node_id=node_id))
        return events

    if direction == "in" and not pending.granted:
        # Recognised and refused, but the body crossed anyway. The old build had no event for
        # this at all - a denied entry just sat un-audited past the initial refusal.
        events.append(GateEvent(kind="denied_crossed", node_id=node_id, person_id=pending.person_id,
                                reason=pending.reason))
        # Consumed, exactly like a granted entry. Leaving it standing meant a refused person
        # who stayed in frame kept the decision alive (process_frame refreshes decided_at while
        # they are still recognised), so EVERY later passage tick re-fired the same alert and
        # re-issued a session token. One crossing is one event.
        state.pending = None
        return events

    # Exit is fail-safe by design: no policy gate on the way out, ever - only whether we know
    # who is leaving. If direction is "out", granted/denied does not apply.
    kind = "entry" if direction == "in" else "exit"
    events.append(GateEvent(kind=kind, node_id=node_id, person_id=pending.person_id))
    state.pending = None  # consumed - a second passage needs its own fresh decision
    return events
