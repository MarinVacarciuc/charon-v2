#!/usr/bin/env python
"""Pre-render every spoken line to a file, once, before the shoot.

    python tools/make_voice.py --cast Marin Natalia Matthew Theya

Nothing about this runs during filming: DEMO_ARCHITECTURE §7 asks for calm, professional,
pre-generated lines with no live LLM and no runtime API, and the cast and script are both
known in advance, so the finite set of lines can simply be baked. That also means the shoot
cannot be broken by a network hiccup or an expired API key, which is the real argument.

macOS `say` with the en_GB voice Daniel - Marin's pick. No key, no account, no per-call cost,
and it is on every Mac, so regenerating the set on the morning of the shoot costs nothing.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
VOICE_DIR = SERVER_DIR / "voice"
VOICE = "Daniel"

# The zones are fixed by the brief (DEMO_ARCHITECTURE §11), so their denial lines are known
# without asking the database.
ZONES = ["Reception", "Warehouse", "Workshop", "Server room"]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def render(text: str, path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["say", "-v", VOICE, "-o", str(path), text],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  FAILED {path.name}: {r.stderr.strip()}", file=sys.stderr)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cast", nargs="*", default=[], help="names to render a welcome line for")
    ap.add_argument("--voice", default=VOICE)
    args = ap.parse_args()
    globals()["VOICE"] = args.voice

    # Check the voice exists before writing anything, so a typo fails loudly and immediately
    # rather than producing a set of files in the wrong voice.
    installed = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    if not any(line.split()[0] == args.voice for line in installed.splitlines() if line.strip()):
        print(f"voice {args.voice!r} is not installed. Available en_GB voices:", file=sys.stderr)
        for line in installed.splitlines():
            if "en_GB" in line:
                print("   ", line.split("#")[0].strip(), file=sys.stderr)
        return 1

    made = 0
    print(f"rendering with voice {args.voice!r} into {VOICE_DIR}")

    for name in args.cast:
        if render(f"Welcome, {name}.", VOICE_DIR / f"welcome_{slug(name)}.aiff"):
            made += 1
            print(f"  welcome_{slug(name)}.aiff")

    for zone in ZONES:
        if render(f"Access denied. {zone}.", VOICE_DIR / f"denied_{slug(zone)}.aiff"):
            made += 1
            print(f"  denied_{slug(zone)}.aiff")

    # Generic fallbacks, so an event involving someone with no personal line still speaks
    # rather than falling silent - a silent system on camera reads as a broken one.
    for key, text in [("granted", "Access granted."),
                      ("denied", "Access denied."),
                      ("unknown", "Unrecognised person."),
                      ("unknown_zone", "Unrecognised person in a restricted zone.")]:
        if render(text, VOICE_DIR / f"{key}.aiff"):
            made += 1
            print(f"  {key}.aiff")

    print(f"\n{made} file(s) written. Re-run after any cast change; it is cheap and offline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
