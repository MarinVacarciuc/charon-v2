# Brain

Consumes the six node streams, runs recognition, owns the single source of truth for
who is where, makes every access decision, drives the dashboard, plays the voice.

Nothing here decides anything on a node, and no node decides anything here.

## Stack, and why

| Choice | Reason |
|---|---|
| Python 3.12 (Homebrew), not the system 3.9 | `asyncio.TaskGroup` for the node supervisor; several pinned libraries have dropped 3.9. The system Python is left untouched. |
| FastAPI + asyncio, one task per node | The previous brain was one threaded server behind a single global lock, so six camera workers serialised against each other and against the HTTP handler. Structure, not language, was the bug source. |
| SQLite (WAL) | Flat JSON per person plus a text audit log was easy to corrupt under concurrent writes. WAL gives concurrent readers for the dashboard with one writer. |
| SSE, not WebSocket | `EventSource` reconnects by itself. Admin actions are naturally request/response, and video tiles are separate image requests anyway. A hand-rolled WS reconnect is the worst thing to be debugging mid-shoot. |

## Setup

```bash
/usr/local/opt/python@3.12/bin/python3.12 -m venv server/.venv
server/.venv/bin/pip install -r server/requirements.txt
cp server/.env.example server/.env      # then fill CHARON_ADMIN_TOKEN
```

The two ONNX models live in `server/models/` (gitignored, ~39 MB):
`face_detection_yunet_2023mar.onnx` and `face_recognition_sface_2021dec.onnx`.

## Run

```bash
server/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8770 --app-dir server
```

## Layout

```
app/config.py         settings from server/.env
app/db/               schema.sql, migrations/, repositories/
app/nodes/            registry, IPv4-explicit resolver, poller + supervisor
app/recognition/      engine (YuNet+SFace), tracker, policy, gate, zones
app/alerts/           dispatcher, telegram, voice
app/push/             SSE hub and event schemas
app/api/              routes, auth
static/               dashboard, gate terminal, staff, settings (plain HTML+JS, no build)
tools/                make_voice.py, seed_demo.py
data/                 charon.db  (gitignored - holds biometric embeddings)
```

## House rules that exist because of specific past bugs

1. **Any name read inside an `except` is assigned before the `try`.** A variable assigned
   only after a fallible call, then read in that call's handler, raises a second exception
   while handling the first and kills the task permanently with no crash log. This killed
   four of six camera workers in one afternoon.
2. **Two separate `try` blocks per poll**: network failure marks the node offline; a frame
   processing failure logs and keeps last-known-good. A processing bug must not be able to
   report a live node as OFFLINE.
3. **Every node task runs under a supervisor** that catches anything, audits it, waits, and
   restarts. "Silently dead forever" has to be structurally impossible, not merely unlikely.
4. **Resolve `.local` names to IPv4 explicitly and cache them.** macOS resolves with
   `AF_UNSPEC`; the ESP32 mDNS responder never answers the AAAA half, so every lookup burns
   the full 5 s IPv6 timeout. Measured: 5.002 s vs 0.010 s.
5. **No implicit "primary camera".** Every camera-scoped action names its node. A shared
   preview that silently swapped feeds, and an enrolment that captured from "whichever
   camera sees a face right now", were two real, separate bugs - the second could enrol a
   stranger under someone else's name and access rights.
6. **Anything that changes strictness persists.** In-memory mode flags revert silently on
   restart and nothing on screen says so.

## Storage and privacy

Face **embeddings** only, never raw images. `server/data/` is gitignored and excluded from
the OneDrive mirror, which is a corporate drive (UK GDPR Art. 9). The backup script fails
loudly rather than reporting success if anything in a forbidden class reaches the mirror.
