"""Face detection and recognition: YuNet (detector) + SFace (128-d embeddings).

Two things this module deliberately does NOT do, both on purpose:

  * It has no idea which face in a frame matters. `detect()` returns every face; picking
    "the largest" or "all of them" is a policy decision that belongs to the caller (gate
    logic wants the largest for the grant plus a tailgating flag on the rest; zone logic
    wants every one of them). Baking "biggest face wins" into the engine was the old
    build's actual blind spot (REBUILD_PROMPT §0.6.5) - a second person in frame was
    invisible to every downstream decision. Keeping the engine face-agnostic makes that
    mistake structurally harder to repeat.
  * It has no idea what counts as "confident enough". `recognise()` reports the facts - the
    best-matching person, their score, and how far ahead they are of the runner-up - and
    `is_confident_match()` is a separate, pure function that turns those facts into a yes/no
    against the live threshold and margin. Keeping the two apart is what makes the threshold
    tunable from config_kv without touching this file, and what makes the decision testable
    with fabricated numbers instead of a camera.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

import cv2
import numpy as np

# SFace's own library default is 0.363; 0.45 was tuned on this exact camera hardware in the
# previous build (own-face scores measured 0.63-0.93) and is the seed value in config_kv.
DEFAULT_SIM_THRESHOLD = 0.45
DEFAULT_SIM_MARGIN = 0.05

# YuNet score/NMS/topK, unchanged from the previous build's tuning.
_YUNET_SCORE_THRESH = 0.7
_YUNET_NMS_THRESH = 0.3
_YUNET_TOP_K = 5000


@dataclass(frozen=True)
class Candidate:
    """What recognise() actually knows, before any threshold is applied."""

    person_id: int | None    # None only when there is nobody enrolled at all
    score: float              # cosine similarity to the best-matching sample, in [-1, 1]
    margin: float             # score minus the best score any OTHER person achieved


def is_confident_match(c: Candidate, threshold: float = DEFAULT_SIM_THRESHOLD,
                       margin: float = DEFAULT_SIM_MARGIN) -> bool:
    """Both conditions matter separately. Threshold alone lets a single bad enrolment sample
    win outright if nobody else is close; margin alone would accept a mediocre match in an
    otherwise-empty roster. The system refuses to name someone it is not sure of - an
    unidentified face is always available as the honest answer."""
    if c.person_id is None:
        return False
    return c.score >= threshold and c.margin >= margin


class RecognitionEngine:
    def __init__(self, yunet_path: str, sface_path: str) -> None:
        # (320, 320) here is a placeholder; detect() sets the real size from each frame.
        self._detector = cv2.FaceDetectorYN.create(
            yunet_path, "", (320, 320), _YUNET_SCORE_THRESH, _YUNET_NMS_THRESH, _YUNET_TOP_K
        )
        self._recognizer = cv2.FaceRecognizerSF.create(sface_path, "")
        # person_id -> every enrolled sample for that person, L2-normalised. A plain dict of
        # lists is a full linear scan per recognise() call, which is fine at the scale this
        # project enrols at (a handful of people, a handful of samples each) - the old build's
        # 56-embedding corpus scanned in well under a millisecond.
        self._samples: dict[int, list[np.ndarray]] = {}

        # One lock around everything that touches the two cv2 objects above, and around the
        # roster dict.
        #
        # Until 2026-09-08 recognition ran directly on the event loop, so it was serialised by
        # accident and therefore safe by accident. Moving it to run_in_executor to unblock the
        # loop removed that accident: six poller tasks can now be inside detect() at the same
        # moment, on one shared OpenCV DNN net, which OpenCV does not promise is safe. detect()
        # is worse than a single call - setInputSize() and detect() are two steps, so two
        # threads holding differently-sized frames can interleave and have one of them detect
        # at the other's dimensions.
        #
        # Serialising costs nothing that was actually wanted. The goal of the executor change
        # was to keep the EVENT LOOP free, not to run inference in parallel; the loop stays
        # free either way, and the measured 1.9 ms worst-case loop gap is unaffected.
        self._cv_lock = threading.RLock()

    # ------------------------------------------------------------------ detection / embedding

    def detect(self, frame: np.ndarray) -> np.ndarray:
        """Every face YuNet finds. Shape (n, 15): x,y,w,h, 5 landmark (x,y) pairs, score.
        Empty array (not None) when nothing is found, so callers never need a None check."""
        h, w = frame.shape[:2]
        with self._cv_lock:
            # setInputSize and detect must not be separable by another thread - see __init__.
            self._detector.setInputSize((w, h))
            _, faces = self._detector.detect(frame)
        if faces is None:
            return np.empty((0, 15), dtype=np.float32)
        return faces

    def embed(self, frame: np.ndarray, face_row: np.ndarray) -> np.ndarray:
        """One face's embedding: aligned via YuNet's landmarks, L2-normalised so that cosine
        similarity is a plain dot product everywhere downstream."""
        with self._cv_lock:
            aligned = self._recognizer.alignCrop(frame, face_row)
            feat = self._recognizer.feature(aligned).flatten().astype(np.float32)
        norm = np.linalg.norm(feat)
        return feat / norm if norm > 0 else feat

    # ------------------------------------------------------------------ the enrolled roster

    # The roster is read from executor threads (recognise, during a frame) and written from
    # the event loop (enrolment, deletion), so it takes the same lock. Without it, an enrolment
    # landing mid-frame can resize the dict while recognise() is iterating it, which raises
    # "dictionary changed size during iteration" - and that exception would surface as a node
    # dropping out, not as anything that points at enrolment.

    def load_samples(self, by_person: dict[int, list[np.ndarray]]) -> None:
        """Replace the whole in-memory roster - called once at startup, and again after any
        enrolment so a newly-added person is recognised on the very next frame."""
        with self._cv_lock:
            self._samples = by_person

    def add_sample(self, person_id: int, vec: np.ndarray) -> None:
        with self._cv_lock:
            self._samples.setdefault(person_id, []).append(vec)

    def sample_count(self, person_id: int) -> int:
        with self._cv_lock:
            return len(self._samples.get(person_id, []))

    @property
    def enrolled_people(self) -> int:
        with self._cv_lock:
            return len(self._samples)

    # ------------------------------------------------------------------ matching

    def recognise(self, vec: np.ndarray) -> Candidate:
        """Best person for this one embedding, aggregated across ALL of their samples by
        taking the max - not the best single sample across the whole roster, which is what
        let one poor enrolment sample win outright in the old build (no per-person
        aggregation at all: `recognise()` there returned the winning SAMPLE's label)."""
        with self._cv_lock:
            # Snapshot under the lock, score outside it: the dot products are the slow part and
            # do not need to hold up an enrolment, but iterating the live dict does.
            roster = [(pid, list(samples)) for pid, samples in self._samples.items() if samples]

        if not roster:
            return Candidate(person_id=None, score=0.0, margin=0.0)

        best_per_person: list[tuple[int, float]] = []
        for pid, samples in roster:
            best = max(float(np.dot(vec, s)) for s in samples)
            best_per_person.append((pid, best))

        if not best_per_person:
            return Candidate(person_id=None, score=0.0, margin=0.0)

        best_per_person.sort(key=lambda kv: kv[1], reverse=True)
        top_id, top_score = best_per_person[0]
        runner_up_score = best_per_person[1][1] if len(best_per_person) > 1 else -1.0
        return Candidate(person_id=top_id, score=top_score, margin=top_score - runner_up_score)
