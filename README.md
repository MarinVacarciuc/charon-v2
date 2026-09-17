# Charon / Cerberus — v2 (ground-up server rebuild)

Smart access-control and personnel-safety system for the **Ezra and Korede Security Ltd**
scenario (BTEC HND Digital Technologies, Unit 21 *Emerging Technologies*).

This is a **fresh, independent repository**. It deliberately does **not** share git history
or a remote with the earlier project at `~/IdeaProjects/charon`, which is left untouched so it
can be worked on in parallel. Reference material (proven node firmware, the ground-truth rebuild
spec, the threat model, the last concept design) was copied in once so this repo stands on its own.

## Why a rebuild

The previous "brain" (`~/charon-spikes/process_server.py`, ~1000 lines) was one monolithic
threaded HTTP server with flat-file storage that accumulated repeated classes of bugs from
reactive growth. This is a considered redesign, not another patch. The full reasoning, locked
decisions, and phased build order live in [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md); the
hardware ground truth (fixed pin maps, network hazards, hard-won lessons) is in
[`docs/REBUILD_PROMPT_2026-07-17.md`](docs/REBUILD_PROMPT_2026-07-17.md).

## Locked architecture

- **One brain, on the Mac** — FastAPI + asyncio (one task per camera node), SSE push to the UI.
- **SQLite** (WAL) for staff / roles / zones / grants / audit / embeddings.
- **6× ESP32-S3** camera + ultrasonic nodes — firmware is proven and carried over as-is.
- **Arduino Uno** — independent physical fail-safe watchdog (heartbeat over USB serial; on
  brain loss it drives a local alert and arms its own ultrasonic backstop). Required by Unit 21 brief.

## Layout

```
firmware/        node firmware (proven) + flash/OTA scripts; uno_watchdog/ added in Phase 5
docs/            rebuild plan, ground-truth spec, prototype notes, concept design
server/          FastAPI brain (added from Phase 2 onward)
scripts/         tooling, incl. one-way OneDrive backup
THREAT_MODEL.md  security posture (Phase 6 hardening baseline)
```

## Backup

`scripts/backup-to-onedrive.sh` mirrors this repo (including `.git`) one-way to
`OneDrive/Leo/charon-v2/` as a backup. It runs automatically after each commit via a
`post-commit` git hook (install with `scripts/install-hooks.sh` after a fresh clone).
Biometric data, secrets, models and caches are excluded from the mirror on purpose — see the
script header. **Never edit files in the OneDrive copy; it is a backup, not a working tree.**

