# Changelog

Checkpoints are cut live, as they are reached, not reconstructed afterwards. Each one is a
real git tag. This is the iteration evidence for P6.

## v0-baseline - 2026-09-02

Groundwork before any system code.

- **Security.** Rotated the shared OTA password; the previous one had been pasted into a
  chat transcript and had to be treated as public. The new value exists only in the
  gitignored `firmware/charon_node/secrets.h`, which `ota_node.sh` reads directly, so it
  never needs to be transcribed anywhere.
- **GDPR.** `scripts/backup-to-onedrive.sh` mirrors the repo to a corporate school drive,
  and its exclude list was narrower than `.gitignore`: an untracked `staff/` directory,
  `.env`, `*.key` or `*.pem` would have been copied there. Rebuilt the exclude list as a
  superset of `.gitignore`, added `--delete-excluded` so a leak is cleaned rather than
  merely stopped, and added a post-run check that fails loudly instead of printing success
  if a forbidden file is present. Audited the existing mirror: clean, so the fix landed
  before any biometric data existed rather than after.
- **Toolchain.** Homebrew Python 3.12.14 alongside the untouched system 3.9.6; venv at
  `server/.venv`; FastAPI, uvicorn, aiosqlite, aiohttp, pydantic-settings, numpy and
  opencv-contrib 5.0.0.93 installed and verified importing. Both ONNX models load from
  `server/models/` in 0.21 s.
- **Docs.** The 18.07 rebuild plan is archived rather than deleted, with a header recording
  what changed and why: it predates the decision that the deliverable is an edited video,
  and its Arduino design put the Uno on USB serial into the Mac, which cannot be filmed
  when the gate is in the yard and the Mac is in the house. `docs/BUILD_PLAN.md` supersedes
  it. `firmware/README.md` was describing a `TRIGGER_DIST_CM` constant that does not exist
  and a UDP path to a phone that is no longer part of the design; rewritten against the
  actual code.

## v1-firmware - in progress

Node firmware v2. Written and compiling (37% flash, 19% RAM); not yet on hardware.

- Camera is **off** until the near sensor trips, and sleeps again after 20 s idle. The
  winning camera pin map is probed once and pinned in NVS, so a wake costs one init rather
  than up to three, and re-probes itself if the pinned map ever stops working.
- New `GET /status`: the whole sensor and health picture as JSON **without touching the
  camera**, so the brain can poll all six nodes continuously while five cameras stay dark.
  Carries the passage counter, and reports the joined `ssid` so a node on the wrong network
  is visible on the dashboard instead of silently unreachable.
- New `GET /wake?sec=` to pre-warm a sleeping camera for the dashboard.
- **Heartbeat square wave on GPIO 21**, asserted only while WiFi is up *and* the brain has
  been heard from within 5 s. This is the single wire the Arduino failover watches; a crash,
  a lost network and a dead brain all collapse it identically.
- **Preferred network by position, not by signal strength.** `WiFiMulti` joins the strongest
  candidate, which on shoot day could pull some boards onto the house router and others onto
  the phone hotspot, with the laptop reachable from only one of them. Entry `[0]` is now
  tried explicitly first, at boot and on every reconnect, and the node moves back to it if it
  returns. Both college SSIDs were dropped from the candidate list entirely.
- Interior boards no longer poll the PASS sensor at all. Nothing is wired to 41/40 there, so
  every other tick was spending the full 25 ms `pulseIn` timeout to learn nothing.
- OTA now drops the camera before accepting an image: flash writes and camera DMA do not mix.
