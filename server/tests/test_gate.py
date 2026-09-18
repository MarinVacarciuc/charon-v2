"""Gate logic tests: fabricated faces and a fake policy_check, no camera, no database."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.recognition.gate import GateNodeState, process_frame, process_passage  # noqa: E402
from app.recognition.observation import FaceObservation  # noqa: E402

MARIN, GUARD_DENIED = 1, 2
T0 = datetime(2026, 9, 3, 12, 0, 0)


def allow_all(person_id, now):
    return True, ""


def deny_all(person_id, now):
    return False, "SUSPENDED"


def known(pid=MARIN, confident=True, area=1000.0):
    return FaceObservation(person_id=pid, confident=confident, area=area)


def unknown():
    return FaceObservation(person_id=None, confident=False)


def confirm(state, node="gate-in", direction="in", n=3, t=T0, faces=None):
    """Feed n identical frames so the tracker commits, per gate.py's tracker.confirm_frames=3."""
    events = []
    for i in range(n):
        events = process_frame(state, node, direction, faces or [known()], allow_all,
                               t + timedelta(milliseconds=300 * i))
    return events


# ---------------------------------------------------------------- decision

def test_decision_fires_once_the_tracker_commits_not_before():
    state = GateNodeState()
    e1 = process_frame(state, "gate-in", "in", [known()], allow_all, T0)
    e2 = process_frame(state, "gate-in", "in", [known()], allow_all, T0 + timedelta(milliseconds=300))
    assert e1 == [] and e2 == []
    e3 = process_frame(state, "gate-in", "in", [known()], allow_all, T0 + timedelta(milliseconds=600))
    assert e3[0].kind == "decision" and e3[0].granted

def test_decision_does_not_refire_every_frame_for_the_same_standing_person():
    state = GateNodeState()
    confirm(state)
    events = process_frame(state, "gate-in", "in", [known()], allow_all, T0 + timedelta(seconds=1))
    assert events == [], "a decision must fire once per commit, not once per frame"

def test_denied_policy_still_produces_a_decision_event():
    state = GateNodeState()
    events = confirm(state)
    assert events[0].kind == "decision" and events[0].granted  # sanity with allow_all
    events3 = []
    st = GateNodeState()
    for i in range(3):
        events3 = process_frame(st, "gate-in", "in", [known()], deny_all,
                                T0 + timedelta(milliseconds=300 * i))
    assert events3[0].kind == "decision" and not events3[0].granted and events3[0].reason == "SUSPENDED"

def test_empty_frame_clears_the_tracker_without_a_stray_decision():
    state = GateNodeState()
    confirm(state)
    events = process_frame(state, "gate-in", "in", [], allow_all, T0 + timedelta(seconds=1))
    assert events == []


# ---------------------------------------------------------------- commit on recognition
# From 2026-09-18 the frame itself commits presence: the PASS sonar was removed from the
# decision path (gate.py's docstring has the measurements). Frames only reach this logic
# while the NEAR sonar sees someone inside one metre, so a commit means recognised AND at
# the gate - but no longer that anyone actually walked through.

def test_granted_recognition_at_gate_in_commits_an_entry_by_itself():
    state = GateNodeState()
    events = confirm(state, "gate-in", "in")
    assert [e.kind for e in events] == ["decision", "entry"]
    assert events[1].person_id == MARIN

def test_refused_recognition_at_gate_in_commits_nothing():
    st = GateNodeState()
    events = []
    for i in range(3):
        events = process_frame(st, "gate-in", "in", [known()], deny_all,
                               T0 + timedelta(milliseconds=300 * i))
    assert [e.kind for e in events] == ["decision"], "a refusal must not put anyone on site"

def test_gate_out_commits_an_exit_even_when_policy_refuses():
    # Exit stays fail-safe: whether someone is allowed IN has no bearing on letting them out.
    st = GateNodeState()
    events = []
    for i in range(3):
        events = process_frame(st, "gate-out", "out", [known()], deny_all,
                               T0 + timedelta(milliseconds=300 * i))
    assert [e.kind for e in events] == ["decision", "exit"]

def test_standing_at_the_gate_commits_once_not_once_per_frame():
    state = GateNodeState()
    confirm(state, "gate-in", "in")
    for i in range(20):  # ~6s of continued confident recognition
        events = process_frame(state, "gate-in", "in", [known()], allow_all,
                               T0 + timedelta(seconds=1, milliseconds=300 * i))
        assert events == [], "one commit per arrival, not one per frame"

def test_a_second_face_in_frame_raises_tailgating_with_the_commit():
    state = GateNodeState()
    events = confirm(state, "gate-in", "in", faces=[known(), known(pid=None, confident=False)])
    kinds = [e.kind for e in events]
    assert kinds == ["decision", "tailgating", "entry"]


# ---------------------------------------------------------------- passage binding (mothballed)
# process_passage is no longer wired to anything - see gate.py's docstring. These stay because
# the sensor is being abandoned for now, not judged worthless, and this is the logic that has
# to still be correct the day it is remounted facing a clear lane.

def test_beat_one_then_beat_two_granted_entry():
    state = GateNodeState()
    confirm(state, t=T0)
    events = process_passage(state, "gate-in", "in", [known()], T0 + timedelta(seconds=1))
    assert len(events) == 1 and events[0].kind == "entry" and events[0].person_id == MARIN

def test_passage_older_binding_window_is_unidentified():
    state = GateNodeState()
    confirm(state, t=T0)
    late = T0 + timedelta(seconds=10)  # BIND_WINDOW_S is 3s
    events = process_passage(state, "gate-in", "in", [known()], late)
    assert events == [type(events[0])(kind="unidentified_passage", node_id="gate-in")]

def test_passage_with_no_decision_at_all_is_unidentified():
    state = GateNodeState()
    events = process_passage(state, "gate-in", "in", [], T0)
    assert len(events) == 1 and events[0].kind == "unidentified_passage"

def test_denied_but_crossed_is_its_own_event():
    # REGRESSION shape: the old build had no event for this at all.
    state = GateNodeState()
    st = GateNodeState()
    for i in range(3):
        process_frame(st, "gate-in", "in", [known()], deny_all, T0 + timedelta(milliseconds=300 * i))
    events = process_passage(st, "gate-in", "in", [known()], T0 + timedelta(seconds=1))
    assert len(events) == 1 and events[0].kind == "denied_crossed" and events[0].person_id == MARIN

def test_denied_but_crossed_only_applies_to_entry_never_to_exit():
    # Exit is fail-safe: no policy gate on the way out, ever.
    st = GateNodeState()
    for i in range(3):
        process_frame(st, "gate-out", "out", [known()], deny_all, T0 + timedelta(milliseconds=300 * i))
    events = process_passage(st, "gate-out", "out", [known()], T0 + timedelta(seconds=1))
    assert len(events) == 1 and events[0].kind == "exit"

def test_passage_consumes_the_pending_decision():
    state = GateNodeState()
    confirm(state, t=T0)
    process_passage(state, "gate-in", "in", [known()], T0 + timedelta(seconds=1))
    assert state.pending is None
    # a second passage with nothing new decided must be unidentified, not a phantom re-entry
    events = process_passage(state, "gate-in", "in", [known()], T0 + timedelta(seconds=1, milliseconds=100))
    assert events[0].kind == "unidentified_passage"

def test_multiple_faces_at_passage_time_raises_tailgating_alongside_the_real_outcome():
    state = GateNodeState()
    confirm(state, t=T0)
    events = process_passage(state, "gate-in", "in", [known(), known(pid=None, confident=False)],
                             T0 + timedelta(seconds=1))
    kinds = [e.kind for e in events]
    assert "tailgating" in kinds and "entry" in kinds

def test_a_fresh_binding_that_keeps_being_reaffirmed_stays_fresh_past_the_original_window():
    # The person keeps standing there, still confidently recognised every frame; decided_at
    # keeps refreshing, so a passage well past the original 3s window is still bound.
    state = GateNodeState()
    confirm(state, t=T0)
    for i in range(20):  # ~6s of continued confident recognition, no NEW commit needed
        process_frame(state, "gate-in", "in", [known()], allow_all, T0 + timedelta(milliseconds=300 * i))
    late_but_reaffirmed = T0 + timedelta(seconds=6.5)
    events = process_passage(state, "gate-in", "in", [known()], late_but_reaffirmed)
    assert events[0].kind == "entry"


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
