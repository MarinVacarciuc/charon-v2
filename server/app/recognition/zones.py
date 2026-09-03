"""Zone occupancy and anomaly detection. Pure: given facts, produces events; no I/O.

Every face in a zone's frame is processed, not just the largest - REBUILD_PROMPT §0.6.5's
lesson applied on the interior side too: a second person in the same shot was previously
invisible to every downstream decision. Here each recognised, on-site person's zone updates
independently, and any unrecognised face is a real anomaly on its own merit, regardless of
how many legitimate faces share the frame.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .observation import FaceObservation

DWELL_S = 2.0             # must be seen continuously this long before the zone actually updates
GAP_RESET_S = 1.0         # a gap shorter than this is jitter, not "they left" - dwell keeps counting
UNKNOWN_THROTTLE_S = 30.0  # per node - a lingering stranger must not flood the feed
WRONG_ZONE_THROTTLE_S = 60.0  # per (person, this zone)


@dataclass
class _PersonTrack:
    seen_since: datetime
    last_seen_at: datetime
    committed: bool = False


@dataclass
class ZoneNodeState:
    """Everything zone logic remembers between frames for one zone node."""

    tracks: dict[int, _PersonTrack] = field(default_factory=dict)
    last_unknown_alert_at: datetime | None = None
    last_wrong_zone_alert_at: dict[int, datetime] = field(default_factory=dict)


@dataclass(frozen=True)
class ZoneEvent:
    kind: str  # zone_update | unknown_in_zone | wrong_zone
    node_id: str
    zone: str
    person_id: int | None = None
    reason: str = ""


def process_frame(state: ZoneNodeState, node_id: str, zone: str, faces: list[FaceObservation],
                  zone_check, now: datetime,
                  dwell_s: float = DWELL_S, unknown_throttle_s: float = UNKNOWN_THROTTLE_S,
                  wrong_zone_throttle_s: float = WRONG_ZONE_THROTTLE_S) -> list[ZoneEvent]:
    """`zone_check(person_id, zone, now) -> (allowed: bool, reason: str)` is
    policy.zone_allowed, injected so this stays testable without a real Person object.

    Known limitation, deliberate for now: a wrong-zone check runs once, at the moment dwell
    commits. A JIT grant that expires while someone continues standing in the same spot will
    not retroactively raise a fresh alert until they leave and dwell again. Acceptable for the
    two-week build; a periodic re-check would close it if it ever matters.
    """
    events: list[ZoneEvent] = []
    seen_this_frame: set[int] = set()
    any_unknown = False

    for f in faces:
        if f.confident and f.person_id is not None:
            pid = f.person_id
            seen_this_frame.add(pid)
            track = state.tracks.get(pid)
            if track is None or (now - track.last_seen_at) > timedelta(seconds=GAP_RESET_S):
                state.tracks[pid] = _PersonTrack(seen_since=now, last_seen_at=now)
            else:
                track.last_seen_at = now
                if not track.committed and (now - track.seen_since) >= timedelta(seconds=dwell_s):
                    track.committed = True
                    events.append(ZoneEvent(kind="zone_update", node_id=node_id, zone=zone, person_id=pid))
                    allowed, reason = zone_check(pid, zone, now)
                    if not allowed:
                        last = state.last_wrong_zone_alert_at.get(pid)
                        if last is None or (now - last) >= timedelta(seconds=wrong_zone_throttle_s):
                            state.last_wrong_zone_alert_at[pid] = now
                            events.append(ZoneEvent(kind="wrong_zone", node_id=node_id, zone=zone,
                                                    person_id=pid, reason=reason))
        else:
            any_unknown = True

    if any_unknown:
        last = state.last_unknown_alert_at
        if last is None or (now - last) >= timedelta(seconds=unknown_throttle_s):
            state.last_unknown_alert_at = now
            events.append(ZoneEvent(kind="unknown_in_zone", node_id=node_id, zone=zone))

    # A real gap (not this-frame jitter) resets that person's dwell; a later re-entry into the
    # same zone re-runs the whole dwell and re-fires zone_update, which is correct - "back in
    # this zone" is a fresh fact, not a continuation of a run that already ended.
    for pid in list(state.tracks):
        if pid not in seen_this_frame and (now - state.tracks[pid].last_seen_at) > timedelta(seconds=GAP_RESET_S):
            del state.tracks[pid]

    return events
