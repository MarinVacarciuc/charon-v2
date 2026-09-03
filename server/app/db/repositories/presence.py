"""Presence and zone-membership writes - the DB side-effects of a gate or zone event.

Kept separate from the pure decision logic in recognition/gate.py and recognition/zones.py
on purpose: those modules decide WHAT happened, this module is the only place that knows how
that gets written to `people`. A gate/zone decision should never need to change if the schema
does, and vice versa.
"""
from __future__ import annotations

import secrets

from ..database import Database, utcnow


def new_session_token() -> str:
    """6 hex chars, same shape as the previous build's `os.urandom(3).hex()` - short enough
    to read off a phone screen, long enough that guessing one is not a real concern for a
    prototype's threat model."""
    return secrets.token_hex(3)


async def commit_entry(db: Database, person_id: int) -> tuple[str, bool]:
    """Flip someone to on-site. Returns (session_token, was_already_in).

    A concurrent entry (already on-site) still commits - a fresh token, a fresh entry_time -
    because refusing to update the record would leave presence stuck on stale data, and the
    caller is expected to raise its own alert using `was_already_in` (REBUILD_PROMPT's threat
    model A2: this is exactly the shape of a cloned-identity or tailgating signal).
    """
    row = await db.fetch_one("SELECT presence FROM people WHERE id = ?", (person_id,))
    was_already_in = bool(row and row["presence"] == "in")
    token = new_session_token()
    await db.execute(
        """
        UPDATE people SET presence = 'in', session_token = ?, entry_time = ?, updated_at = ?
        WHERE id = ?
        """,
        (token, utcnow(), utcnow(), person_id),
    )
    return token, was_already_in


async def commit_exit(db: Database, person_id: int) -> bool:
    """Flip someone off-site, annul their token, clear their zone. Returns whether they were
    actually on-site beforehand - `False` is the "exit without entry" anomaly (A1/A2's mirror
    case: a stolen phone or a double-exit, not a normal departure)."""
    row = await db.fetch_one("SELECT presence FROM people WHERE id = ?", (person_id,))
    was_in = bool(row and row["presence"] == "in")
    await db.execute(
        """
        UPDATE people SET presence = 'out', session_token = '', at_zone_id = NULL,
                          overstay_alerted_at = '', updated_at = ?
        WHERE id = ?
        """,
        (utcnow(), person_id),
    )
    return was_in


async def set_zone(db: Database, person_id: int, zone_name: str) -> None:
    await db.execute(
        "UPDATE people SET at_zone_id = (SELECT id FROM zones WHERE name = ?), updated_at = ? WHERE id = ?",
        (zone_name, utcnow(), person_id),
    )
