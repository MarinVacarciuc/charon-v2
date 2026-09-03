"""Speak a pre-rendered line, without ever blocking the event loop or overlapping itself.

Playback runs on one dedicated OS thread draining a queue, for two reasons. `afplay` is a
blocking subprocess, so calling it from async code would stall every node's polling for the
length of the line - and two lines started at once would talk over each other, which sounds
broken on camera in a way that a slightly late line does not.

Nothing here generates audio. The finite set of lines is baked before the shoot by
tools/make_voice.py; a missing file is logged and skipped rather than falling back to
synthesis at runtime, because a line that was never pre-rendered is a script change nobody
made on purpose.
"""
from __future__ import annotations

import logging
import queue
import re
import subprocess
import threading
from pathlib import Path

log = logging.getLogger(__name__)

# A line that has waited longer than this has been overtaken by events - saying "welcome" ten
# seconds after someone walked through is worse than saying nothing.
MAX_AGE_S = 6.0


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


class VoicePlayer:
    def __init__(self, voice_dir: Path, enabled: bool = True) -> None:
        self._dir = voice_dir
        self._enabled = enabled
        self._q: queue.Queue[tuple[Path, float]] = queue.Queue(maxsize=16)
        self._thread = threading.Thread(target=self._run, name="voice", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        import time
        while True:
            path, queued_at = self._q.get()
            if time.monotonic() - queued_at > MAX_AGE_S:
                log.debug("dropping stale voice line %s", path.name)
                continue
            try:
                subprocess.run(["afplay", str(path)], capture_output=True, timeout=20)
            except Exception:  # noqa: BLE001
                log.exception("failed to play %s", path.name)

    def _say_file(self, name: str) -> None:
        if not self._enabled:
            return
        path = self._dir / f"{name}.aiff"
        if not path.exists():
            log.warning("no pre-rendered voice line %r - run tools/make_voice.py", name)
            return
        import time
        try:
            self._q.put_nowait((path, time.monotonic()))
        except queue.Full:
            log.warning("voice queue full, dropping %r", name)

    # ------------------------------------------------------------------ the script

    def welcome(self, person_name: str) -> None:
        """Per-person line if one was rendered, generic 'access granted' if not - a guest who
        joined the cast late still gets spoken to."""
        personal = self._dir / f"welcome_{slug(person_name)}.aiff"
        self._say_file(f"welcome_{slug(person_name)}" if personal.exists() else "granted")

    def denied_zone(self, zone: str) -> None:
        specific = self._dir / f"denied_{slug(zone)}.aiff"
        self._say_file(f"denied_{slug(zone)}" if specific.exists() else "denied")

    def denied(self) -> None:
        self._say_file("denied")

    def unknown(self) -> None:
        self._say_file("unknown")

    def unknown_in_zone(self) -> None:
        self._say_file("unknown_zone")
