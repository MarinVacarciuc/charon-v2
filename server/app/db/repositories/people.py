"""Minimal person CRUD - just enough for enrolment today. Editing access (role, hours,
zones, JIT grants) is Day 6/8 territory and lands in this file when that work starts, not
speculatively now.
"""
from __future__ import annotations

from ..database import Database, utcnow


async def get_role_id(db: Database, role_name: str) -> int | None:
    return await db.fetch_value("SELECT id FROM roles WHERE name = ?", (role_name,))


async def get_by_name(db: Database, name: str) -> dict | None:
    row = await db.fetch_one("SELECT * FROM people WHERE name = ?", (name,))
    return dict(row) if row else None


async def get_by_id(db: Database, person_id: int) -> dict | None:
    row = await db.fetch_one("SELECT * FROM people WHERE id = ?", (person_id,))
    return dict(row) if row else None


async def create(db: Database, name: str, role_name: str, telegram_chat_id: str = "") -> int:
    role_id = await get_role_id(db, role_name)
    if role_id is None:
        raise ValueError(f"unknown role '{role_name}'")
    now = utcnow()
    return await db.execute(
        """
        INSERT INTO people (name, role_id, telegram_chat_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, role_id, telegram_chat_id, now, now),
    )


async def get_or_create(db: Database, name: str, role_name: str) -> int:
    """Enrolment's entry point: a repeat capture for an existing name adds a sample rather
    than creating a duplicate person, since enrolling "a few angles and lightings" is
    normal and expected (REBUILD_PROMPT §10)."""
    existing = await get_by_name(db, name)
    if existing is not None:
        return existing["id"]
    return await create(db, name, role_name)


async def list_all(db: Database) -> list[dict]:
    rows = await db.fetch_all(
        """
        SELECT p.*, r.name AS role_name
        FROM people p JOIN roles r ON r.id = p.role_id
        ORDER BY p.name
        """
    )
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ policy loading
#
# Bridges the DB's row-shaped world to recognition/policy.py's pure Person dataclass. Kept
# here, not in policy.py, because policy.py must stay free of any database dependency - that
# is what makes its 19 tests run with no DB and no camera.

from datetime import date as _date, datetime as _datetime, time as _time  # noqa: E402

from ...recognition import policy as _policy  # noqa: E402


def _parse_time(s: str) -> _time:
    h, m = s.split(":")
    return _time(int(h), int(m))


def _parse_date(s: str) -> _date | None:
    if not s:
        return None
    return _date.fromisoformat(s)


def _parse_datetime(s: str) -> _datetime | None:
    if not s:
        return None
    return _datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


async def load_policy_person(db: Database, person_id: int) -> _policy.Person | None:
    """Everything policy.policy_ok / policy.zone_allowed need for one person, assembled from
    people + person_zone_overrides + zone_grants. Active grants only (revoked_at IS NULL);
    an already-expired grant is filtered by policy.py's own active_grants() at decision time,
    not here, so "expired versus revoked" stays a policy-layer distinction, not a query one.
    """
    row = await db.fetch_one(
        """
        SELECT p.*, r.name AS role_name
        FROM people p JOIN roles r ON r.id = p.role_id
        WHERE p.id = ?
        """,
        (person_id,),
    )
    if row is None:
        return None

    overrides = await db.fetch_all(
        "SELECT z.name FROM person_zone_overrides o JOIN zones z ON z.id = o.zone_id WHERE o.person_id = ?",
        (person_id,),
    )
    grants = await db.fetch_all(
        """
        SELECT z.name AS zone, g.expires_at
        FROM zone_grants g JOIN zones z ON z.id = g.zone_id
        WHERE g.person_id = ? AND g.revoked_at IS NULL
        """,
        (person_id,),
    )

    return _policy.Person(
        name=row["name"],
        role=row["role_name"],
        status=row["status"],
        hours_from=_parse_time(row["hours_from"]),
        hours_to=_parse_time(row["hours_to"]),
        valid_until=_parse_date(row["valid_until"]),
        access_until=_parse_datetime(row["access_until"]),
        max_hours=row["max_hours"],
        zone_overrides={r["name"] for r in overrides},
        grants=[_policy.ZoneGrant(zone=g["zone"], expires_at=_parse_datetime(g["expires_at"]))
                for g in grants],
    )


async def load_role_zones(db: Database, role_name: str) -> set[str]:
    rows = await db.fetch_all(
        """
        SELECT z.name FROM role_zone_defaults d
        JOIN roles r ON r.id = d.role_id JOIN zones z ON z.id = d.zone_id
        WHERE r.name = ?
        """,
        (role_name,),
    )
    return {r["name"] for r in rows}
