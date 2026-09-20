#!/usr/bin/env python
"""Read the Uno's failover journal over USB and fold it into the brain's audit log.

    python tools/import_uno_log.py --port /dev/cu.usbmodemXXXX --outage-start "2026-09-14 14:32:00"

This is the reconciliation step the design deliberately cannot automate. The Uno has no
network; its only neighbour with one is the gate ESP32, which sits on the far side of a
one-way wire and is, in the demo's own scenario, the thing being killed. So the fallback keeps
its own journal and hands it over when somebody comes to collect it. That is the honest price
of independence: a truly independent backstop cannot report on itself.

The Uno has no clock either, so its records are offsets in seconds from its own boot.
--outage-start anchors them to real time. Without it the rows still import, timed from the
brain's clock at import, and are marked as approximate rather than quietly pretending.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
from pathlib import Path

import serial

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings          # noqa: E402
from app.db.database import Database         # noqa: E402
from app.db.repositories import audit        # noqa: E402

OUTCOME_SEVERITY = {
    "granted": ("uno_failover_entry", "alert"),
    "denied": ("uno_failover_denied", "alert"),
    "approach_no_card": ("uno_failover_no_card", "alert"),
    # A recognised card that never completed its PIN (added 2026-09-20 with the second
    # factor). Distinct from "denied" on purpose: this is a card on the list that failed the
    # second check, not a card that was never on it, and the two should not read the same way
    # in the audit log.
    "pin_fail": ("uno_failover_pin_fail", "alert"),
}


def clear_journal(port: str, baud: int = 9600) -> bool:
    """Erase the board's journal. Only ever called AFTER the rows are safely in the database.

    That order is the whole point. Clearing first, or clearing on the assumption the import
    worked, turns any crash in between into permanently lost security records - and they are
    unrecoverable by construction, because this board is the only place they ever existed.
    """
    import time
    with serial.Serial(port, baud, timeout=1) as ser:
        time.sleep(2.0)
        ser.reset_input_buffer()
        ser.write(b"CLEAR\n")
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            line = ser.readline().decode("utf-8", "replace").strip()
            if line.startswith("JOURNAL_CLEARED"):
                return True
    return False


def read_journal(port: str, baud: int = 9600, timeout_s: float = 12.0) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    meta: dict = {}
    with serial.Serial(port, baud, timeout=1) as ser:
        # Opening the port resets an Uno, so wait out the bootloader before talking to it -
        # a command sent too early is simply swallowed and looks like the board ignoring you.
        import time
        time.sleep(2.0)
        ser.reset_input_buffer()
        ser.write(b"D\n")

        deadline = time.monotonic() + timeout_s
        started = False
        while time.monotonic() < deadline:
            line = ser.readline().decode("utf-8", "replace").strip()
            if not line:
                continue
            if line.startswith("JOURNAL_BEGIN"):
                parts = line.split(",")
                meta = {"count": int(parts[1]),
                        "capacity": parts[2].split("=")[1],
                        "wrapped": parts[3].split("=")[1] == "1"}
                started = True
                continue
            if line.startswith("JOURNAL_END"):
                break
            if not started or line.startswith("uid,"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) != 3:
                continue
            rows.append({"uid": parts[0], "seconds": int(parts[1]), "outcome": parts[2]})
    return rows, meta


async def import_rows(rows: list[dict], meta: dict, anchor: dt.datetime | None, exact: bool) -> int:
    settings = get_settings()
    db = Database(settings.db_path, settings.migrations_dir)
    await db.connect()

    # Card UIDs are not identities to the brain: the roster knows faces, not cards. So a row
    # names the card, not a person, and says so - inventing a person from a UID would be a
    # guess presented as a fact.
    if meta.get("wrapped"):
        await audit.record(
            db, "uno_journal_wrapped",
            f"Uno failover journal had wrapped: it holds the most recent {meta['count']} "
            f"records and older ones were overwritten",
            severity="warn", actor="reconciliation")

    n = 0
    for r in rows:
        event_type, severity = OUTCOME_SEVERITY.get(r["outcome"], ("uno_failover_event", "warn"))
        when = anchor + dt.timedelta(seconds=r["seconds"]) if anchor else None
        stamp = when.strftime("%Y-%m-%d %H:%M:%S") if when else "time unknown"
        approx = "" if exact else " (offset from the board's own boot, not anchored to real time)"
        if r["outcome"] == "approach_no_card":
            msg = f"during a smart-path outage somebody approached the gate and presented no card at {stamp}{approx}"
        elif r["outcome"] == "granted":
            msg = f"during a smart-path outage the gate failover admitted card {r['uid']} at {stamp}{approx}"
        elif r["outcome"] == "pin_fail":
            msg = f"during a smart-path outage card {r['uid']} was recognised but its PIN was wrong or not entered in time at {stamp}{approx}"
        else:
            msg = f"during a smart-path outage the gate failover refused unknown card {r['uid']} at {stamp}{approx}"
        await audit.record(db, event_type, msg, severity=severity, actor="reconciliation",
                           details={"uid": r["uid"], "seconds_since_boot": r["seconds"],
                                    "outcome": r["outcome"], "anchored": exact})
        n += 1

    await db.close()
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--outage-start", default=None,
                    help='when the board booted / the outage began, "YYYY-MM-DD HH:MM:SS"')
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--clear", action="store_true",
                    help="erase the board's journal once the rows are safely imported")
    args = ap.parse_args()

    anchor = None
    if args.outage_start:
        anchor = dt.datetime.strptime(args.outage_start, "%Y-%m-%d %H:%M:%S")

    rows, meta = read_journal(args.port)
    if not meta:
        print("No journal header seen. Is this the Uno, and is it running the watchdog sketch?",
              file=sys.stderr)
        return 1

    print(f"journal: {meta['count']} record(s), capacity {meta['capacity']}, "
          f"wrapped={meta['wrapped']}")
    for r in rows:
        when = (anchor + dt.timedelta(seconds=r["seconds"])).strftime("%H:%M:%S") if anchor \
               else f"+{r['seconds']}s"
        print(f"  {when}  {r['outcome']:18s} {r['uid']}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    if not rows:
        print("\nnothing to import")
        return 0
    if anchor is None:
        print("\nNo --outage-start given: rows will be imported without real timestamps and "
              "marked approximate.")

    n = asyncio.run(import_rows(rows, meta, anchor, exact=anchor is not None))
    print(f"\nimported {n} record(s) into audit_log")

    if args.clear:
        # Deliberately after the import returned, not alongside it. The board is the only
        # place these records exist until this point.
        if clear_journal(args.port):
            print("board journal cleared - the next outage starts from empty")
        else:
            print("WARNING: the board did not confirm the erase. The rows ARE imported; the "
                  "journal still holds them and will be imported again unless you clear it.",
                  file=sys.stderr)
            return 1
    else:
        print("board journal left intact (pass --clear to erase it now that it is imported)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
