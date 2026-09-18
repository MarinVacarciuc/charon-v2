"""Live, in-memory state for one node.

Deliberately separate from the `nodes` table. The table holds what an operator configured
(where the board is, how it is mounted, what its thresholds should be); this holds what is
true right now (is it answering, is its camera up, what was the last frame). Configuration
survives a restart and live state does not, and conflating the two is how a stale "online"
flag ends up persisted.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NodeLive:
    node_id: str
    hostname: str
    role: str                      # gate-in | gate-out | zone
    zone: str | None = None
    rotation_deg: int = 0

    online: bool = False
    last_seen: float = 0.0         # monotonic
    last_status: dict[str, Any] = field(default_factory=dict)

    # Latest frame as served by the node, kept so the dashboard can be fed from the brain
    # rather than every open browser tab polling the board directly.
    last_frame: bytes | None = None
    last_frame_at: float = 0.0
    # Face boxes found in the most recently PROCESSED frame, in that frame's own pixel
    # coordinates (it is already rotated, and detection ran on the rotated copy, so the two
    # always share an orientation). Carries person_id rather than a name: the dashboard
    # already holds the roster, so resolving the name there costs nothing and avoids a
    # database read per face per frame. Detection finishes just after the frame is published,
    # so a viewer can catch boxes one frame behind - about 90 ms, a few pixels of drift.
    last_faces: list[dict[str, Any]] = field(default_factory=list)

    cam_on: bool = False
    # True while an operator has asked (via the node's /wake) to keep frames coming from a
    # doorway nobody is standing in. Since 2026-09-13 the camera no longer sleeps, so this is
    # no longer "is it warming up" - it is "fetch frames even though nobody is in range".
    hold: bool = False
    near: bool = False
    near_cm: float = -1.0
    pass_cm: float = -1.0
    passages: int | None = None    # None until the first reading establishes a baseline

    consecutive_errors: int = 0
    last_error: str = ""
    restarts: int = 0              # how many times the supervisor has revived this task

    @property
    def is_gate(self) -> bool:
        return self.role in ("gate-in", "gate-out")

    @property
    def direction(self) -> str | None:
        """Which way a passage through this node means. A property of the physical lane, never
        a global mode toggle: the old build had a manual entry/exit switch that applied to
        whichever camera happened to be primary."""
        if self.role == "gate-in":
            return "in"
        if self.role == "gate-out":
            return "out"
        return None

    def age_s(self) -> float:
        if self.last_seen == 0.0:
            return float("inf")
        return time.monotonic() - self.last_seen

    def frame_age_s(self) -> float:
        if self.last_frame_at == 0.0:
            return float("inf")
        return time.monotonic() - self.last_frame_at

    def ui_state(self) -> str:
        """The three states the dashboard must never confuse.

        "live" used to mean the camera was powered. Since the camera stopped sleeping that
        would be true of every online node at all times, which tells an operator nothing. It
        now means what the operator actually wants to know: this node is looking at somebody
        right now, either because they are inside recognition range or because the operator
        asked for a look. An online node with an empty doorway is "armed", exactly as before.
        """
        if not self.online:
            return "offline"
        return "live" if (self.near or self.hold) else "armed"

    def wants_frames(self) -> bool:
        """Whether the brain should be pulling frames from this node this tick.

        The single place that decision is expressed. Recognition range replaced camera power
        as the gate: with six cameras now permanently initialised, keying off cam_on would
        have every node streaming continuously into recognition for no reason.
        """
        return self.cam_on and (self.near or self.hold)
