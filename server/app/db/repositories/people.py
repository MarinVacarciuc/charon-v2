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
