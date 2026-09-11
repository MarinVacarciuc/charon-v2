"""RecognitionEngine matching logic, with fabricated unit vectors - no camera, no model
files. detect()/embed() themselves need real ONNX models and are exercised separately
against a live camera frame (see the manual verification in docs/REPORT_NOTES.md); what is
tested here is the pure arithmetic: aggregation and the confidence decision.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from app.recognition.engine import Candidate, RecognitionEngine, is_confident_match  # noqa: E402

MARIN, NATALIA, THEYA = 1, 2, 3


def unit(*coords) -> np.ndarray:
    v = np.array(coords, dtype=np.float32)
    return v / np.linalg.norm(v)


def _engine_with(samples: dict[int, list[np.ndarray]]) -> RecognitionEngine:
    e = object.__new__(RecognitionEngine)  # skip __init__: no model files needed for matching-only tests
    e._samples = {}
    # __init__ is skipped, so the roster lock has to be supplied by hand. The matching path
    # takes it on every call (added 2026-09-11, when recognition moved onto executor threads
    # and the shared roster stopped being serialised by the event loop).
    e._cv_lock = threading.RLock()
    e.load_samples(samples)
    return e


# ---------------------------------------------------------------- aggregation by person

def test_empty_roster_returns_no_candidate():
    e = _engine_with({})
    c = e.recognise(unit(1, 0, 0))
    assert c.person_id is None

def test_exact_match_scores_one():
    v = unit(1, 0, 0)
    e = _engine_with({MARIN: [v]})
    c = e.recognise(v)
    assert c.person_id == MARIN
    assert abs(c.score - 1.0) < 1e-6

def test_aggregation_is_max_over_a_persons_samples_not_the_single_best_sample_globally():
    # REGRESSION: the old engine's recognise() picked the winning SAMPLE across the whole
    # roster with no per-person step at all, so a person with one lucky sample could win over
    # someone with several good ones. Here Marin's best individual sample (0.99) must win
    # even though Natalia's single sample (0.9) is, sample for sample, higher than Marin's
    # WORST sample - the aggregation has to take marin's own max, not get confused by scale.
    probe = unit(1, 0, 0)
    marin_samples = [unit(1, 0, 0.02), unit(0.9, 0.1, 0.1)]   # best ~0.9998
    natalia_samples = [unit(0.9, 0.2, 0.1)]                    # ~0.9535
    e = _engine_with({MARIN: marin_samples, NATALIA: natalia_samples})
    c = e.recognise(probe)
    assert c.person_id == MARIN
    assert c.score > 0.99

def test_margin_is_gap_to_the_best_OTHER_person_not_to_the_second_sample_of_the_winner():
    # A person with many samples must not be penalised in their own margin by their own
    # second-best sample - margin compares across PEOPLE, never within one person's list.
    probe = unit(1, 0, 0)
    e = _engine_with({
        MARIN: [unit(1, 0, 0), unit(0.1, 0.9, 0.1)],  # own second sample scores low - irrelevant
        NATALIA: [unit(0.5, 0.5, 0.0)],
    })
    c = e.recognise(probe)
    assert c.person_id == MARIN
    natalia_score = float(np.dot(probe, unit(0.5, 0.5, 0.0)))
    assert abs(c.margin - (1.0 - natalia_score)) < 1e-6

def test_a_person_with_zero_samples_is_never_returned():
    e = _engine_with({MARIN: [], NATALIA: [unit(1, 0, 0)]})
    c = e.recognise(unit(1, 0, 0))
    assert c.person_id == NATALIA

def test_three_way_roster_picks_the_true_closest():
    probe = unit(1, 0, 0)
    e = _engine_with({
        MARIN: [unit(0, 1, 0)],
        NATALIA: [unit(1, 0, 0)],
        THEYA: [unit(0.7, 0.7, 0)],
    })
    c = e.recognise(probe)
    assert c.person_id == NATALIA


# ---------------------------------------------------------------- is_confident_match

def test_below_threshold_is_never_confident():
    c = Candidate(person_id=MARIN, score=0.30, margin=0.50)
    assert not is_confident_match(c, threshold=0.45, margin=0.05)

def test_below_margin_is_never_confident_even_with_a_high_score():
    # A high absolute score against an ALSO-high runner-up is exactly the ambiguous case a
    # margin check exists to catch - e.g. near-identical twins, or a poor enrolment overlap.
    c = Candidate(person_id=MARIN, score=0.80, margin=0.02)
    assert not is_confident_match(c, threshold=0.45, margin=0.05)

def test_clears_both_bars_is_confident():
    c = Candidate(person_id=MARIN, score=0.70, margin=0.10)
    assert is_confident_match(c, threshold=0.45, margin=0.05)

def test_no_candidate_is_never_confident_regardless_of_numbers():
    c = Candidate(person_id=None, score=0.99, margin=0.99)
    assert not is_confident_match(c)

def test_exactly_at_both_bars_is_confident_inclusive():
    c = Candidate(person_id=MARIN, score=0.45, margin=0.05)
    assert is_confident_match(c, threshold=0.45, margin=0.05)


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
