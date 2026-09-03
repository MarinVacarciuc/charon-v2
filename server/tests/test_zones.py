"""Zone logic tests: fabricated faces and a fake zone_check, no camera, no database."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.recognition.observation import FaceObservation  # noqa: E402
from app.recognition.zones import ZoneNodeState, process_frame  # noqa: E402

MARIN, NATALIA = 1, 2
ZONE = "Server room"
T0 = datetime(2026, 9, 3, 12, 0, 0)


def allow_all(pid, zone, now):
    return True, ""


def deny_all(pid, zone, now):
    return False, "ZONE NOT ALLOWED"


def known(pid=MARIN):
    return FaceObservation(person_id=pid, confident=True)


def unknown():
    return FaceObservation(person_id=None, confident=False)


def dwell(state, faces, zone_check=allow_all, t=T0, seconds=2.5, step=0.3):
    """Feed frames every `step` seconds for `seconds` total - enough to clear DWELL_S=2.0.
    Returns every event from every frame in the run, not just the last: zone_update commits
    mid-run (once dwell first clears), and later frames in the same run legitimately return
    nothing further - a caller that only kept the last frame's events would miss it."""
    events = []
    n = int(seconds / step) + 1
    for i in range(n):
        events += process_frame(state, "zone-server", ZONE, faces, zone_check,
                                t + timedelta(seconds=step * i))
    return events


# ---------------------------------------------------------------- dwell / commit

def test_no_update_before_dwell_elapses():
    state = ZoneNodeState()
    events = process_frame(state, "zone-server", ZONE, [known()], allow_all, T0)
    assert events == []
    events = process_frame(state, "zone-server", ZONE, [known()], allow_all, T0 + timedelta(seconds=0.5))
    assert events == [], "well under the 2s dwell"

def test_update_fires_once_dwell_elapses_then_never_again_for_the_same_run():
    state = ZoneNodeState()
    seen_update = []
    for i in range(12):  # ~3.6s of continuous presence
        events = process_frame(state, "zone-server", ZONE, [known()], allow_all,
                               T0 + timedelta(milliseconds=300 * i))
        seen_update += [e for e in events if e.kind == "zone_update"]
    assert len(seen_update) == 1, f"expected exactly one zone_update, got {len(seen_update)}"

def test_a_single_frame_gap_does_not_reset_the_dwell_timer():
    state = ZoneNodeState()
    # Continuous ~0.3s polling; the frame at 0.6s is a genuine miss (detector had a bad
    # frame), not a real departure - the run must still commit around the 2.0s dwell mark.
    times = [0.0, 0.3, 0.6, 0.9, 1.2, 1.5, 1.8, 2.1, 2.4]
    fired = []
    for i, dt in enumerate(times):
        faces = [] if i == 2 else [known()]
        fired += process_frame(state, "zone-server", ZONE, faces, allow_all, T0 + timedelta(seconds=dt))
    assert any(e.kind == "zone_update" for e in fired), \
        "dwell should have survived the single missed frame and still committed"

def test_a_real_gap_resets_dwell_and_re_entry_fires_again():
    state = ZoneNodeState()
    dwell(state, [known()])  # first visit, commits
    # they leave for well over GAP_RESET_S
    process_frame(state, "zone-server", ZONE, [], allow_all, T0 + timedelta(seconds=5))
    # they come back
    events = dwell(state, [known()], t=T0 + timedelta(seconds=10))
    assert any(e.kind == "zone_update" for e in events), "re-entry after a real gap must re-fire"

def test_walking_past_in_transit_never_commits():
    state = ZoneNodeState()
    events = process_frame(state, "zone-server", ZONE, [known()], allow_all, T0)
    events += process_frame(state, "zone-server", ZONE, [], allow_all, T0 + timedelta(seconds=0.3))
    assert not any(e.kind == "zone_update" for e in events)


# ---------------------------------------------------------------- multi-face

def test_every_recognised_face_updates_independently_not_just_the_largest():
    # REGRESSION shape: REBUILD_PROMPT §0.6.5 - the old build only ever looked at one face.
    state = ZoneNodeState()
    events = dwell(state, [known(MARIN), known(NATALIA)])
    updated = {e.person_id for e in events if e.kind == "zone_update"}
    assert updated == {MARIN, NATALIA}

def test_unknown_face_alongside_known_ones_still_raises_its_own_alert():
    state = ZoneNodeState()
    events = dwell(state, [known(MARIN), unknown()])
    kinds = [e.kind for e in events]
    assert "zone_update" in kinds and "unknown_in_zone" in kinds


# ---------------------------------------------------------------- unknown-face throttle

def test_unknown_alert_is_throttled_per_node_not_per_frame():
    state = ZoneNodeState()
    fires = []
    for i in range(20):  # ~6s of a lingering stranger, well past a naive per-frame alert
        events = process_frame(state, "zone-server", ZONE, [unknown()], allow_all,
                               T0 + timedelta(milliseconds=300 * i))
        fires += [e for e in events if e.kind == "unknown_in_zone"]
    assert len(fires) == 1, f"expected 1 alert in 6s (throttle=30s), got {len(fires)}"

def test_unknown_alert_fires_again_after_the_throttle_window():
    state = ZoneNodeState()
    e1 = process_frame(state, "zone-server", ZONE, [unknown()], allow_all, T0)
    e2 = process_frame(state, "zone-server", ZONE, [unknown()], allow_all, T0 + timedelta(seconds=31))
    assert any(e.kind == "unknown_in_zone" for e in e1)
    assert any(e.kind == "unknown_in_zone" for e in e2)


# ---------------------------------------------------------------- wrong-zone throttle

def test_wrong_zone_alert_fires_once_on_commit_with_a_denying_policy():
    state = ZoneNodeState()
    events = dwell(state, [known(MARIN)], zone_check=deny_all)
    kinds = [e.kind for e in events]
    assert kinds.count("wrong_zone") == 1
    assert kinds.count("zone_update") == 1, "the zone still updates - a violation is recorded, not hidden"

def test_wrong_zone_alert_is_throttled_per_person_per_zone():
    state = ZoneNodeState()
    dwell(state, [known(MARIN)], zone_check=deny_all, t=T0)
    process_frame(state, "zone-server", ZONE, [], allow_all, T0 + timedelta(seconds=5))  # they leave
    events = dwell(state, [known(MARIN)], zone_check=deny_all, t=T0 + timedelta(seconds=10))
    assert not any(e.kind == "wrong_zone" for e in events), "still inside the 60s throttle window"

def test_allowed_zone_never_raises_wrong_zone():
    state = ZoneNodeState()
    events = dwell(state, [known(MARIN)], zone_check=allow_all)
    assert not any(e.kind == "wrong_zone" for e in events)


def _run() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn(); print(f"  ok   {name}")
        except AssertionError as e:
            failed.append(name); print(f"  FAIL {name}  {e}")
        except Exception as e:  # noqa: BLE001
            failed.append(name); print(f"  ERR  {name}  {type(e).__name__}: {e}")
    print(f"\n{len(tests)-len(failed)}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
