"""Registry loading, against a real (temporary) database, no network involved.

The full poller lifecycle - online detection, fault isolation when one node dies, offline
detection timing - was already verified against real hardware in this session (see
docs/REPORT_NOTES.md): a live board taken down, the rest of the fleet unaffected, timing
measured. What is worth a permanent, hardware-free test is the seam this module owns: does
the `nodes` table actually turn into the right NodeLive objects.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiohttp

from app.db.database import Database
from app.nodes.registry import NodeRegistry


async def main() -> int:
    db_path = Path("/tmp/charon_registry_smoke.db")
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)
    db = Database(db_path, Path("app/db/migrations"))
    await db.connect()

    async with aiohttp.ClientSession() as session:
        registry = NodeRegistry(db, session)
        await registry.load()

        all_nodes = registry.all()
        assert len(all_nodes) == 6, f"expected 6 seeded nodes, got {len(all_nodes)}"

        gate_in = registry.get("gate-in")
        assert gate_in is not None
        assert gate_in.hostname == "gate-in.local"
        assert gate_in.role == "gate-in"
        assert gate_in.zone is None
        assert gate_in.is_gate and gate_in.direction == "in"

        gate_out = registry.get("gate-out")
        assert gate_out.direction == "out"

        zone_server = registry.get("zone-server")
        assert zone_server is not None
        assert zone_server.role == "zone"
        assert zone_server.zone == "Server room", f"got zone={zone_server.zone!r}"
        assert not zone_server.is_gate and zone_server.direction is None

        # Every node starts unpolled: offline, no frame, no baseline passage count yet.
        for n in all_nodes:
            assert not n.online
            assert n.last_frame is None
            assert n.passages is None
            assert n.ui_state() == "offline"

        assert registry.get("no-such-node") is None

    await db.close()
    print("registry smoke test: PASS (6 nodes loaded, roles/zones/directions correct)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
