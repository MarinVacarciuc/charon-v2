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
    """The roster, with the role and current zone resolved to NAMES rather than ids - the
    dashboard groups people into zone columns by name, and making it join ids client-side
    would put the zone list in a second place that can disagree with the database."""
    rows = await db.fetch_all(
        """
        SELECT p.*, r.name AS role_name, z.name AS zone_name
        FROM people p
        JOIN roles r ON r.id = p.role_id
        LEFT JOIN zones z ON z.id = p.at_zone_id
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


# ------------------------------------------------------------------ editing and grants

EDITABLE = ("role", "telegram_chat_id", "hours_from", "hours_to",
            "valid_until", "access_until", "max_hours", "status", "is_dispatcher")


async def update(db: Database, person_id: int, fields: dict) -> None:
    """Apply an allow-listed set of edits.

    The allow-list is the point: `presence`, `session_token`, `entry_time` and `at_zone_id`
    are system-managed and must never be settable through an edit form, or an operator could
    hand someone a session by typing one in. Same discipline as the previous build's FIELDS
    split, kept deliberately.
    """
    sets, params = [], []
    for key, value in fields.items():
        if key not in EDITABLE:
            continue
        if key == "role":
            role_id = await get_role_id(db, value)
            if role_id is None:
                raise ValueError(f"unknown role '{value}'")
            sets.append("role_id = ?")
            params.append(role_id)
        else:
            sets.append(f"{key} = ?")
            params.append(value)
    if not sets:
        return
    sets.append("updated_at = ?")
    params.append(utcnow())
    params.append(person_id)
    await db.execute(f"UPDATE people SET {', '.join(sets)} WHERE id = ?", params)


async def set_zone_overrides(db: Database, person_id: int, zone_names: list[str]) -> None:
    """Replace this person's zone overrides wholesale.

    An empty list means "inherit the role" - which is NOT the same as "no zones", and the
    difference matters: policy.permanent_zones() treats a non-empty override set as a full
    replacement in both directions, so an override list that narrows is how you restrict
    someone below their role (the authorisation gap the old build had, where an ADMIN could
    not be restricted at all).
    """
    statements: list[tuple[str, tuple]] = [
        ("DELETE FROM person_zone_overrides WHERE person_id = ?", (person_id,))
    ]
    for name in zone_names:
        statements.append((
            "INSERT INTO person_zone_overrides (person_id, zone_id) "
            "SELECT ?, id FROM zones WHERE name = ?",
            (person_id, name),
        ))
    await db.execute_many(statements)


async def delete(db: Database, person_id: int) -> None:
    # Embeddings and overrides and grants all cascade (ON DELETE CASCADE), so the biometric
    # data goes with the person - which is the GDPR-relevant behaviour, not an accident.
    await db.execute("DELETE FROM people WHERE id = ?", (person_id,))


async def grant_zone(db: Database, person_id: int, zone_name: str, minutes: int,
                     granted_by: str = "admin") -> str:
    """Issue (or replace) a just-in-time pass for one zone. Returns the expiry timestamp.

    Each zone carries its own expiry and lapses on its own - there is no revert step to
    forget, which is the whole privilege-creep argument (threat model A4). Replacing an
    existing live grant rather than stacking keeps "how long is left" unambiguous.
    """
    from datetime import datetime, timedelta, timezone
    expires = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    await db.execute_many([
        ("UPDATE zone_grants SET revoked_at = ? WHERE person_id = ? AND revoked_at IS NULL "
         "AND zone_id = (SELECT id FROM zones WHERE name = ?)", (utcnow(), person_id, zone_name)),
        ("INSERT INTO zone_grants (person_id, zone_id, expires_at, granted_by, granted_at) "
         "SELECT ?, id, ?, ?, ? FROM zones WHERE name = ?",
         (person_id, expires, granted_by, utcnow(), zone_name)),
    ])
    return expires


async def revoke_zone(db: Database, person_id: int, zone_name: str | None) -> None:
    """Revoke one zone's grant, or every live grant when zone_name is None."""
    if zone_name is None:
        await db.execute(
            "UPDATE zone_grants SET revoked_at = ? WHERE person_id = ? AND revoked_at IS NULL",
            (utcnow(), person_id))
    else:
        await db.execute(
            "UPDATE zone_grants SET revoked_at = ? WHERE person_id = ? AND revoked_at IS NULL "
            "AND zone_id = (SELECT id FROM zones WHERE name = ?)",
            (utcnow(), person_id, zone_name))


async def live_grants(db: Database, person_id: int) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT z.name AS zone, g.expires_at FROM zone_grants g JOIN zones z ON z.id = g.zone_id "
        "WHERE g.person_id = ? AND g.revoked_at IS NULL ORDER BY g.expires_at",
        (person_id,))
    return [dict(r) for r in rows]
