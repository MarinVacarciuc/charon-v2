"""Regressions for the seven defects confirmed by the 2026-09-11 pre-shoot review.

Each test fails against the code as it stood that morning. They are grouped here rather than
scattered because they share one origin: a review that was run twice, hit the session limit
both times, and left findings that had to be verified by hand.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from app.recognition import policy  # noqa: E402
from app.recognition.engine import Candidate, RecognitionEngine  # noqa: E402
from app.recognition.gate import GateNodeState, process_frame, process_passage  # noqa: E402
from app.recognition.observation import FaceObservation  # noqa: E402

MARIN = 1
T0 = dt.datetime(2026, 9, 11, 12, 0, 0)


def deny_all(pid, now):
    return False, "SUSPENDED"


def known(pid=MARIN):
    return FaceObservation(person_id=pid, confident=True, area=1000.0)


# ---------------------------------------------------------------- 1. policy clock is local

def test_policy_clock_is_local_not_utc():
    """Hours are typed by a person meaning local time; comparing them against a UTC clock put
    every window out by the offset. In BST a Cleaner limited to 18:00-20:00 was still admitted
    at 20:30 local, because the system thought it was 19:30."""
    drift = abs((policy.policy_now() - dt.datetime.now()).total_seconds())
    assert drift < 2, f"policy clock is {drift:.0f}s from the wall clock - it is not local"


def test_stored_utc_converts_to_local_for_policy():
    stored = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    converted = policy.to_policy_time(stored)
    assert abs((converted - dt.datetime.now()).total_seconds()) < 2


# ---------------------------------------------------------------- 2. denied_crossed consumes

def test_denied_crossed_consumes_the_pending_decision():
    """It used to return without clearing state.pending. Because process_frame keeps
    refreshing decided_at while the person is still in frame, every later passage tick
    re-fired the same alert and re-issued a session token - an alert storm on camera."""
    st = GateNodeState()
    for i in range(3):
        process_frame(st, "gate-in", "in", [known()], deny_all, T0 + dt.timedelta(milliseconds=300 * i))
    first = process_passage(st, "gate-in", "in", [known()], T0 + dt.timedelta(seconds=1))
    assert [e.kind for e in first] == ["denied_crossed"]
    assert st.pending is None, "the refused decision must be consumed, exactly like a granted one"

    second = process_passage(st, "gate-in", "in", [known()], T0 + dt.timedelta(seconds=1, milliseconds=200))
    assert [e.kind for e in second] == ["unidentified_passage"], \
        "a second crossing with nothing newly decided must not re-fire denied_crossed"


# ---------------------------------------------------------------- 3. engine is thread-safe

def test_engine_roster_survives_mutation_during_matching():
    """recognise() iterated the live roster dict. Since recognition moved onto executor
    threads, an enrolment landing mid-frame could resize it underneath - RuntimeError
    "dictionary changed size during iteration", surfacing as a node dropping out."""
    e = object.__new__(RecognitionEngine)
    e._samples = {}
    e._cv_lock = threading.RLock()
    v = np.ones(128, dtype=np.float32) / np.sqrt(128)
    e.load_samples({i: [v] for i in range(200)})

    errors = []

    def churn():
        try:
            for i in range(200, 600):
                e.add_sample(i, v)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def match():
        try:
            for _ in range(300):
                e.recognise(v)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=churn), threading.Thread(target=match)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"concurrent enrolment and matching raised: {errors[:2]}"


# ---------------------------------------------------------------- 4. empty hours do not raise

def test_empty_hours_do_not_raise():
    """Clearing a time field on the Staff page wrote "" and _parse_time raised straight out of
    load_policy_person, through the frame pipeline, past the poller's network-only handler and
    into the supervisor - which restarted the task every 2s forever, because the bad row was
    still there. One cleared field took a node off the air permanently."""
    from app.db.repositories.people import _parse_time
    assert _parse_time("", dt.time(0, 0)) == dt.time(0, 0)
    assert _parse_time("nonsense", dt.time(23, 59)) == dt.time(23, 59)
    assert _parse_time("18:30", dt.time(0, 0)) == dt.time(18, 30)   # still parses real values


# ---------------------------------------------------------------- 5. telegram keeps references

def test_telegram_keeps_a_reference_to_in_flight_sends():
    """asyncio holds only a weak reference to a running task, so a bare create_task() could be
    garbage-collected mid-send - the message silently never arrives. That is the phone half of
    beats 1 and 5."""
    from app.alerts.telegram import Telegram

    async def main():
        sent = []

        class FakeSession:
            def post(self, *a, **k):
                sent.append(k.get("data"))
                raise RuntimeError("not actually sending")

        tg = Telegram("token", FakeSession())
        tg.send("123", "hello")
        assert len(tg._inflight) == 1, "the in-flight task must be referenced, not left weak"
        await asyncio.sleep(0.05)
        assert len(tg._inflight) == 0, "and released once it finishes"

    asyncio.run(main())


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
