"""Background sweep: who is still on site past when they should have left.

A person who does not leave is the one anomaly nobody triggers - no camera sees an event, no
sensor fires, nothing happens. It is the absence of an event, so the only way to catch it is
to go looking on a timer. That is why this is a sweep rather than a reaction.

The deadline itself is computed by policy.overstay_deadline, which is pure and tested,
including the case that broke the previous build: a shift that ends after midnight. Anchoring
to the entry timestamp rather than to "today" is what makes that work.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

from ..db.database import Database, utcnow
from ..db.repositories import audit, people
from ..push import events as ev
from ..push.hub import SseHub
from ..recognition import policy

log = logging.getLogger(__name__)

SWEEP_INTERVAL_S = 30.0


class OverstayWatch:
    def __init__(self, db: Database, hub: SseHub, telegram=None) -> None:
        self._db = db
        self._hub = hub
        self._tg = telegram

    async def run(self) -> None:
        while True:
            try:
                await self.sweep()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                # Same discipline as the node pollers: a sweep that throws must not end the
                # loop, or overstay detection silently stops for the rest of the session.
                log.exception("overstay sweep failed; continuing")
            await asyncio.sleep(SWEEP_INTERVAL_S)

    async def sweep(self) -> None:
        grace = int(float(await self._db.fetch_value(
            "SELECT value FROM config_kv WHERE key='overstay_grace_min'", default="5")))
        # Local, for the same reason as the gate: overstay_deadline() combines the entry
        # moment with the person's hours_to, which is a local wall-clock time. Comparing a
        # UTC clock against it put every deadline out by the current offset.
        now = policy.policy_now()

        rows = await self._db.fetch_all(
            "SELECT id, name, entry_time, overstay_alerted_at FROM people "
            "WHERE presence = 'in' AND entry_time != ''")
        for row in rows:
            if row["overstay_alerted_at"]:
                continue  # one alert per stay; cleared on exit and on a take reset
            try:
                entry = policy.to_policy_time(row["entry_time"])   # stored UTC -> local
            except ValueError:
                continue

            person = await people.load_policy_person(self._db, row["id"])
            if person is None:
                continue
            deadline = policy.overstay_deadline(entry, person, grace_minutes=grace)
            if deadline is None or now < deadline:
                continue

            over_by = int((now - deadline).total_seconds() // 60)
            await self._db.execute(
                "UPDATE people SET overstay_alerted_at = ? WHERE id = ?", (utcnow(), row["id"]))
            await audit.record(
                self._db, "overstay",
                f"{row['name']} is still on site {over_by} min past their expected departure "
                f"(entered {row['entry_time']})",
                severity="alert", person_id=row["id"])
            await self._hub.publish(ev.alert(
                "overstay", f"{row['name']}: {over_by} min past expected departure",
                person_id=row["id"]))

            full = await people.get_by_id(self._db, row["id"])
            if self._tg and full and full.get("telegram_chat_id"):
                self._tg.send(full["telegram_chat_id"],
                              f"CHARON\n\n{row['name']}, you are still recorded as on site past "
                              f"your expected departure. Please sign out at the gate.")
            log.info("overstay: %s (%d min over)", row["name"], over_by)
