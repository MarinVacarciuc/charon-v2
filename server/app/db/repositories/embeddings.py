"""Face embedding storage: BLOB round-trip and the roster load the engine needs at startup.

Stored as raw float32 bytes (`ndarray.tobytes()`), not a text/JSON encoding - the previous
build's rationale carries over unchanged: this is 512 bytes for a 128-d vector, and storing
embeddings rather than images is itself the GDPR-relevant choice (non-reversible to a photo).
`model_version` is stamped on every row for exactly one reason: recognisers are not
interchangeable, and a future engine swap must not silently start comparing old vectors
against new ones - a version mismatch should be loud, not a slow accuracy regression nobody
can explain.
"""
from __future__ import annotations

import numpy as np

from ..database import Database, utcnow

MODEL_VERSION = "sface-2021dec"


def _to_blob(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def _from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


async def add(db: Database, person_id: int, vec: np.ndarray, *, source: str,
              node_id: str | None = None, model_version: str = MODEL_VERSION) -> int:
    if source not in ("live", "photo"):
        raise ValueError(f"source must be 'live' or 'photo', got {source!r}")
    return await db.execute(
        """
        INSERT INTO face_embeddings (person_id, vec, dim, model_version, source, node_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (person_id, _to_blob(vec), int(vec.shape[0]), model_version, source, node_id, utcnow()),
    )


async def load_all(db: Database, *, model_version: str = MODEL_VERSION) -> dict[int, list[np.ndarray]]:
    """Every embedding, grouped by person, for the engine's startup warm-load.

    Filtered to the current model_version on purpose: a stray embedding from a retired
    recogniser must not silently participate in matching just because the row is still in
    the table.
    """
    rows = await db.fetch_all(
        "SELECT person_id, vec FROM face_embeddings WHERE model_version = ?",
        (model_version,),
    )
    out: dict[int, list[np.ndarray]] = {}
    for row in rows:
        out.setdefault(row["person_id"], []).append(_from_blob(row["vec"]))
    return out


async def count_for(db: Database, person_id: int) -> int:
    return await db.fetch_value(
        "SELECT count(*) FROM face_embeddings WHERE person_id = ?", (person_id,), default=0
    )
