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

## Unreleased - 2026-09-02, after v0-baseline

- **OTA authentication removed by decision.** v0-baseline rotated the shared OTA password;
  it has now been dropped entirely and wireless updates are unauthenticated. The password is
  compiled into the image, so it has to stay in sync between `secrets.h` and whatever is
  already running on each board, and a mismatch does not fail gracefully: it locks that
  board out of wireless updates and forces it off the wall for a USB flash. On a private
  hotspot, over a fourteen-day build with six wall-mounted boards, that availability hazard
  costs more than the threat it defends against. Recorded as a documented limitation in
  `docs/REPORT_NOTES.md` alongside the production position (signed images, not merely
  authenticated ones). Threat model C4 moves from *planned* to *consciously declined*.
- Added `docs/REPORT_NOTES.md`: running evidence for the report, written as decisions are
  made. Carries the measurements taken so far and an explicit list of numbers inherited from
  the old project that must be re-measured on this build rather than quoted second-hand.

## Unreleased - 2026-09-03, fleet provisioning day

All six boards flashed and identified by MAC via tools/provision_node.py, which
refuses to guess an identity for a MAC it does not recognise. All six verified
individually and then, for the first time, simultaneously on battery power on
the demo hotspot: correct node id, correct MAC, camera pin map found, correct
pass-sensor role for their position, joined the network.

Found and fixed a real bug in the WiFi preferred-network logic added in
v0-baseline: a board on a non-preferred network ran a full WiFi scan every 5
seconds trying to find the preferred one, and scanning steals airtime from the
current connection. Measured on gate-in while it sat on the fallback network:
32% request failure rate, 857 ms median latency, spikes to 5.2 s, four
consecutive failures at the run's end. Replaced the automatic periodic scan
with an on-demand GET /rejoin the operator calls once during setup, after the
hotspot is confirmed on, instead of an ambient poll that fights the radio
forever. Not yet pushed to the boards (see below); dormant while all six sit
on the preferred network, since the scanning branch only runs while connected
to a fallback.

Found, chased, and closed out (as a documented limitation, not a bug) a UDP
problem: OTA firmware updates fail over the demo hotspot specifically. The
handshake is UDP request/response on port 3232; every other path the brain
depends on (/status, /shot.jpg, /threshold, /led, /wake) is plain HTTP over TCP
and works reliably over the same hotspot. Ruled out: the Mac firewall (off),
VPN interference (routing to the hotspot subnet is direct, no tunnel), and
authentication (mDNS correctly advertises auth_upload=no). The remaining
explanation is a known limitation of phone-based hotspots relaying
client-to-client UDP. USB remains the fallback for any firmware push made on
this hotspot; in-place threshold recalibration is unaffected, since it is
ordinary HTTP. This is the exact hazard REBUILD_PROMPT flagged as unresolved
("the demo hotspot SSID was never finalised") and DEMO_ARCHITECTURE called the
single biggest risk to the shoot - now measured. Fixed ota_node.sh separately
to pass the upload tool's required (but here unauthenticated) password field,
and to explain the hotspot failure mode instead of a bare non-zero exit when
it does fail there.

Measured fleet-wide load for the first time: six boards clustered on a bench,
all cameras awake simultaneously (each board's near sensor tripped by
proximity to the others), contending for one hotspot's airtime. Zero request
failures, but latency far less even than an isolated board (up to 2.1 s on one
node, against 20-67 ms isolated) and die temperature elevated fleet-wide
(65.5-80.6 C, against 63.6-66.6 C for one board cycling normally). This is a
bench artifact from physical clustering, not the expected running condition
once boards are spread across the yard per their mounting positions, which is
what the camera-off-by-default design targets. The 1.5 s status timeout held
under this worst case with zero failures, so it stands as measured.

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
- OTA drops the camera before accepting an image: flash writes and camera DMA do not mix.
- OTA is unauthenticated by decision (see the entry above).
