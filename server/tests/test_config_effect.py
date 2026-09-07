"""Settings must CHANGE BEHAVIOUR, not merely persist.

This test exists because a review found seven of ten settings were written, audited as
changed, and read by nothing: the page said "saved", the value survived a restart, and the
running system ignored it. Persistence was verified at the time; effect was not. So this
asserts effect.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import Database                    # noqa: E402
from app.db.repositories import config                  # noqa: E402
from app.recognition import gate, zones                 # noqa: E402
from app.recognition.observation import FaceObservation # noqa: E402
from app.recognition.tracker import IdentityTracker     # noqa: E402

MARIN = 1
T0 = dt.datetime(2026, 9, 7, 12, 0, 0)
allow = lambda *a: (True, "")
known = lambda: FaceObservation(person_id=MARIN, confident=True)


def test_confirm_frames_changes_when_an_identity_commits():
    t = IdentityTracker(confirm_frames=3)
    assert t.observe(MARIN) is None and t.observe(MARIN) is None
    t2 = IdentityTracker(confirm_frames=1)
    assert t2.observe(MARIN) == MARIN, "confirm_frames=1 must commit on the first frame"

def test_confirm_frames_can_be_lowered_on_a_running_tracker():
    t = IdentityTracker(confirm_frames=5)
    for _ in range(3):
        t.observe(MARIN)
    assert t.committed is None
    t.set_confirm_frames(3)                 # operator lowers it in the yard
    assert t.observe(MARIN) == MARIN, "an already-accumulated streak should satisfy the new bar"

def test_gate_bind_window_is_honoured():
    st = gate.GateNodeState()
    for i in range(3):
        gate.process_frame(st, "gate-in", [known()], allow, T0 + dt.timedelta(milliseconds=300*i))
    late = T0 + dt.timedelta(seconds=8)
    # default 3s window: too late to bind
    assert gate.process_passage(gate_copy(st), "gate-in", "in", [known()], late)[0].kind \
        == "unidentified_passage"
    # widened window: binds
    assert gate.process_passage(gate_copy(st), "gate-in", "in", [known()], late,
                                bind_window_s=20.0)[0].kind == "entry"

def gate_copy(st):
    import copy
    return copy.deepcopy(st)

def test_dwell_is_honoured():
    slow = zones.ZoneNodeState()
    fast = zones.ZoneNodeState()
    fired_slow = fired_fast = False
    for i in range(5):                       # 1.2s of presence at 0.3s intervals
        t = T0 + dt.timedelta(milliseconds=300 * i)
        fired_slow |= any(e.kind == "zone_update" for e in
                          zones.process_frame(slow, "z", "Server room", [known()], allow, t))
        fired_fast |= any(e.kind == "zone_update" for e in
                          zones.process_frame(fast, "z", "Server room", [known()], allow, t,
                                              dwell_s=0.5))
    assert not fired_slow, "the default 2s dwell must NOT commit within 1.2s"
    assert fired_fast, "a 0.5s dwell must commit within 1.2s"

def test_unknown_throttle_is_honoured():
    tight = zones.ZoneNodeState()
    n = 0
    for i in range(6):
        t = T0 + dt.timedelta(seconds=i)
        n += sum(1 for e in zones.process_frame(tight, "z", "Server room",
                                                [FaceObservation(None, False)], allow, t,
                                                unknown_throttle_s=2.0)
                 if e.kind == "unknown_in_zone")
    assert n >= 3, f"a 2s throttle over 6s should fire about 3 times, got {n}"


async def _db_roundtrip():
    p = Path("/tmp/charon_config_effect.db")
    for sfx in ("", "-wal", "-shm"):
        Path(f"{p}{sfx}").unlink(missing_ok=True)
    db = Database(p, Path("app/db/migrations"))
    await db.connect()
    assert await config.get_int(db, "confirm_frames", 99) == 3, "seeded value should be read"
    await db.execute("UPDATE config_kv SET value='7' WHERE key='confirm_frames'")
    config.invalidate()
    assert await config.get_int(db, "confirm_frames", 99) == 7, "a write must be visible"
    assert await config.get_bool(db, "voice_enabled", False) is True
    await db.execute("UPDATE config_kv SET value='0' WHERE key='voice_enabled'")
    config.invalidate()
    assert await config.get_bool(db, "voice_enabled", True) is False, "0 must read as off"
    assert await config.get_float(db, "no_such_key", 1.25) == 1.25, "missing key falls back"
    await db.close()

def test_config_reads_and_invalidation():
    asyncio.run(_db_roundtrip())


def _run() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
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
