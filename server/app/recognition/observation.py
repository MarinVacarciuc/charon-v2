"""One face's fact for this frame, downstream of engine.Candidate + is_confident_match.

Gate and zone logic both consume a list of these and neither needs to know anything about
YuNet, SFace, or cosine similarity - only "is this a specific known person, confidently,
right now." Keeping this as the shared boundary is what makes both gate.py and zones.py
testable with fabricated lists instead of real frames.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FaceObservation:
    person_id: int | None      # None when unknown OR not confident enough
    confident: bool
    area: float = 0.0          # box w*h; callers sort largest-first before handing gate.py the list
