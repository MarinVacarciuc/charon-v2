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

    cam_on: bool = False
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

        A sleeping camera is not a broken one, and the old build gave an operator no way to
        tell them apart at a glance.
        """
        if not self.online:
            return "offline"
        return "live" if self.cam_on else "armed"
