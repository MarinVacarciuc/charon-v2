"""IdentityTracker tests: pure state machine, no camera needed."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.recognition.tracker import IdentityTracker  # noqa: E402

MARIN, NATALIA = 1, 2


def test_nothing_committed_before_confirm_frames():
    t = IdentityTracker(confirm_frames=3)
    assert t.observe(MARIN) is None
    assert t.observe(MARIN) is None
    assert t.observe(MARIN) == MARIN

def test_alternating_candidates_never_commit():
    # REGRESSION shape: this is exactly the frame-to-frame jitter DEMO_ARCHITECTURE flags -
    # a bouncing raw signal must never accidentally satisfy the gate.
    t = IdentityTracker(confirm_frames=3)
    for _ in range(10):
        assert t.observe(MARIN) is None
        assert t.observe(NATALIA) is None

def test_a_single_stray_miss_does_not_drop_a_committed_identity():
    t = IdentityTracker(confirm_frames=3)
    for _ in range(3):
        t.observe(MARIN)
    assert t.committed == MARIN
    assert t.observe(None) == MARIN          # one blink / bad frame
    assert t.observe(MARIN) == MARIN         # recovers immediately, no re-confirmation needed

def test_a_sustained_run_of_misses_clears_the_commitment():
    t = IdentityTracker(confirm_frames=3)
    for _ in range(3):
        t.observe(MARIN)
    assert t.committed == MARIN
    for _ in range(2):
        t.observe(None)
    assert t.committed == MARIN, "not yet - only 2 consecutive misses"
    assert t.observe(None) is None, "3rd consecutive miss clears it"

def test_handoff_to_a_different_person_needs_its_own_full_run():
    t = IdentityTracker(confirm_frames=3)
    for _ in range(3):
        t.observe(MARIN)
    assert t.committed == MARIN
    assert t.observe(NATALIA) == MARIN,  "1 frame of Natalia must not steal the commit"
    assert t.observe(NATALIA) == MARIN,  "2 frames still not enough"
    assert t.observe(NATALIA) == NATALIA, "3rd consecutive frame hands off cleanly"

def test_confirm_frames_of_one_commits_immediately():
    t = IdentityTracker(confirm_frames=1)
    assert t.observe(MARIN) == MARIN

def test_reset_clears_everything():
    t = IdentityTracker(confirm_frames=2)
    t.observe(MARIN); t.observe(MARIN)
    assert t.committed == MARIN
    t.reset()
    assert t.committed is None
    assert t.observe(MARIN) is None  # needs a fresh full run after reset

def test_rejects_nonsense_config():
    try:
        IdentityTracker(confirm_frames=0)
        assert False, "should have raised"
    except ValueError:
        pass


def _run() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn(); print(f"  ok   {name}")
        except AssertionError as e:
            failed.append(name); print(f"  FAIL {name}  {e}")
    print(f"\n{len(tests)-len(failed)}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
