"""Frame-to-frame confidence gating: an identity is only trusted once it wins K consecutive
frames, and stays trusted until something else wins K consecutive frames in its place.

Same two-variable candidate-plus-agreement-count shape as the firmware's ultrasonic debounce
(`pollSonar` in charon_node.ino) - a candidate value accumulates agreement, and only replaces
the committed value once it has earned enough of it. There, it stops a noisy sensor reading
from being trusted; here, it stops a single blink, bad angle, or momentary lighting flicker
from being read as "this person left" or "this is actually someone else."

Deliberately does not need a separate "how many misses before we drop the commit" parameter:
`None` (no confident match this frame) is treated as just another candidate value, so it goes
through the exact same K-consecutive-frames gate as any real identity. A single stray miss
leaves the last committed identity in place; only a genuine run of misses clears it - the
identity does not chatter every time recognition confidence dips near the threshold, which is
precisely the frame-to-frame jitter DEMO_ARCHITECTURE §4 calls out.
"""
from __future__ import annotations


class IdentityTracker:
    def __init__(self, confirm_frames: int = 3) -> None:
        if confirm_frames < 1:
            raise ValueError("confirm_frames must be at least 1")
        self._confirm_frames = confirm_frames
        self._candidate: int | None = None
        self._agree = 0
        self._committed: int | None = None

    def set_confirm_frames(self, n: int) -> None:
        """Change the threshold on a running tracker. A LOWER value can satisfy an
        already-accumulated streak immediately, which is intended: an operator lowering it in
        the yard wants the next frame to behave, not a fresh run of agreement."""
        if n >= 1:
            self._confirm_frames = n

    def observe(self, raw_person_id: int | None) -> int | None:
        """Feed one frame's raw recognition result. Returns the currently committed identity
        (None if nothing has earned commitment yet, including "confirmed absent")."""
        if raw_person_id == self._candidate:
            self._agree += 1
        else:
            self._candidate = raw_person_id
            self._agree = 1
        if self._agree >= self._confirm_frames:
            self._committed = self._candidate
        return self._committed

    @property
    def committed(self) -> int | None:
        return self._committed

    def reset(self) -> None:
        self._candidate = None
        self._agree = 0
        self._committed = None
