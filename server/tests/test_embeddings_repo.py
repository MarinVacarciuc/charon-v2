"""Embedding storage round-trip and the roster load, against a real temporary database."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from app.db.database import Database  # noqa: E402
from app.db.repositories import embeddings, people  # noqa: E402


async def main() -> int:
    db_path = Path("/tmp/charon_embeddings_test.db")
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)
    db = Database(db_path, Path("app/db/migrations"))
    await db.connect()

    # ---- people: create, then get_or_create must not duplicate ----
    pid = await people.get_or_create(db, "Marin", "GUARD")
    pid2 = await people.get_or_create(db, "Marin", "GUARD")
    assert pid == pid2, "get_or_create duplicated a person on a repeat enrolment"

    other_pid = await people.create(db, "Natalia", "IT")
    assert other_pid != pid

    try:
        await people.create(db, "X", "NOT-A-REAL-ROLE")
        assert False, "should have rejected an unknown role"
    except ValueError:
        pass

    # ---- embeddings: byte-exact round trip ----
    original = np.random.default_rng(42).standard_normal(128).astype(np.float32)
    original = original / np.linalg.norm(original)
    await embeddings.add(db, pid, original, source="live", node_id="gate-in")
    await embeddings.add(db, pid, original * 0.5, source="photo")  # second sample, unnormalised on purpose

    n = await embeddings.count_for(db, pid)
    assert n == 2, f"expected 2 samples, got {n}"

    roster = await embeddings.load_all(db)
    assert pid in roster and len(roster[pid]) == 2
    assert other_pid not in roster, "Natalia has no embeddings yet, must not appear"

    recovered = roster[pid][0]
    assert recovered.dtype == np.float32
    assert np.allclose(recovered, original, atol=1e-6), "BLOB round-trip lost precision"

    # ---- model_version isolation: a different version must not be loaded together ----
    await embeddings.add(db, pid, original, source="live", model_version="some-older-model")
    roster_current = await embeddings.load_all(db)  # default filter = current MODEL_VERSION
    assert len(roster_current[pid]) == 2, "an old-model embedding leaked into the current roster"

    try:
        await embeddings.add(db, pid, original, source="raw-photo-not-a-real-source")
        assert False, "should have rejected an invalid source"
    except ValueError:
        pass

    await db.close()
    print("embeddings/people repo test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
