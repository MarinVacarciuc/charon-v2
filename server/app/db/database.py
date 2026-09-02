"""SQLite access: one connection, WAL, and a migration runner.

Why one connection and one lock rather than a pool: the write volume here is a handful of
rows per person-movement, and a single writer removes a whole class of concurrency bugs for
free. WAL is what keeps that from blocking the dashboard, since readers do not wait for the
writer.

The lock is deliberately kept from the old design. The old build's global lock was not the
problem; the problem was that recognition ran *inside* it, so six camera workers serialised
against each other. Here the lock covers database mutations only, and inference happens off
the event loop entirely.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import aiosqlite

log = logging.getLogger(__name__)

_MIGRATION_RE = re.compile(r"^(\d{3})_.+\.sql$")


def utcnow() -> str:
    """One timestamp format everywhere: sortable as text, which is what the queries rely on."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path: Path, migrations_dir: Path) -> None:
        self._path = path
        self._migrations_dir = migrations_dir
        self._conn: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()

    # ------------------------------------------------------------------ lifecycle

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        # WAL: concurrent readers while one writer works. foreign_keys is OFF by default in
        # SQLite and has to be asked for per connection, which is easy to forget and quietly
        # turns every REFERENCES clause into documentation.
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.commit()
        await self._migrate()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("database not connected; call connect() first")
        return self._conn

    # ------------------------------------------------------------------ migrations

    def _migration_files(self) -> list[tuple[int, Path]]:
        found: list[tuple[int, Path]] = []
        for p in sorted(self._migrations_dir.glob("*.sql")):
            m = _MIGRATION_RE.match(p.name)
            if not m:
                log.warning("ignoring unrecognised migration filename: %s", p.name)
                continue
            found.append((int(m.group(1)), p))
        return found

    async def _applied_versions(self) -> set[int]:
        # The table only exists after 001 has run, so a fresh database has to answer "none"
        # rather than raising.
        cur = await self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        )
        if await cur.fetchone() is None:
            return set()
        cur = await self.conn.execute("SELECT version FROM schema_migrations")
        return {row["version"] for row in await cur.fetchall()}

    async def _migrate(self) -> None:
        applied = await self._applied_versions()
        for version, path in self._migration_files():
            if version in applied:
                continue
            log.info("applying migration %s", path.name)
            sql = path.read_text(encoding="utf-8")
            async with self._write_lock:
                # executescript commits any open transaction first, so the bookkeeping row is
                # written separately and both are committed together.
                await self.conn.executescript(sql)
                await self.conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, utcnow()),
                )
                await self.conn.commit()
            log.info("migration %s applied", path.name)

    # ------------------------------------------------------------------ queries

    async def fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(sql, params)
        return list(await cur.fetchall())

    async def fetch_one(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Row | None:
        cur = await self.conn.execute(sql, params)
        return await cur.fetchone()

    async def fetch_value(self, sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
        row = await self.fetch_one(sql, params)
        return default if row is None else row[0]

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Run one mutating statement. Returns lastrowid."""
        async with self._write_lock:
            cur = await self.conn.execute(sql, params)
            await self.conn.commit()
            return cur.lastrowid or 0

    async def execute_many(self, statements: Iterable[tuple[str, Sequence[Any]]]) -> None:
        """Run several statements as one transaction: all of them, or none."""
        async with self._write_lock:
            try:
                for sql, params in statements:
                    await self.conn.execute(sql, params)
                await self.conn.commit()
            except Exception:
                await self.conn.rollback()
                raise
