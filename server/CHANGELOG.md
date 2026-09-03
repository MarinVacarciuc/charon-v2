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

## v3.2-decisions - 2026-09-03

Gate and zone decision logic, wired end to end into the running brain.

app/recognition/gate.py (pure, no I/O): recognition names someone and issues a
decision (BEAT 1); presence only flips when the pass ultrasonic's counter
actually increments (BEAT 2) - the model Marin locked in over the original
camera-only proposal, since the gate is where the demo's actual physical
sensor gets a real job. A decision stays bound to a later passage within a
3s window that keeps refreshing as long as the same person is still
confidently recognised, so someone who pauses and is reaffirmed for several
seconds is still correctly bound, not falsely treated as stale. Two new event
kinds the old build never had: denied_crossed (recognised, refused, walked
through anyway) and unidentified_passage now fires symmetrically at both
entry and exit, not just entry. Tailgating (>1 face at the passage instant)
is its own alert alongside the real outcome. 12 unit tests.

app/recognition/zones.py (pure, no I/O): every face in frame is processed,
not just the largest (REBUILD_PROMPT §0.6.5's named blind spot) - each
recognised person's zone updates independently after a ~2s dwell (a single
missed frame does not reset the dwell timer; a real >1s gap does, and a later
re-entry re-fires correctly), and any unrecognised face raises its own
throttled alert regardless of how many legitimate faces share the frame.
Wrong-zone alerts are throttled per (person, zone) pair, unknown-face alerts
per node. 12 unit tests.

app/db/repositories/presence.py: the DB side of a decided gate/zone outcome -
session tokens, presence flips, zone assignment - kept deliberately separate
from the pure decision logic, so a schema change and a policy change are
never the same edit. app/db/repositories/people.py gained
load_policy_person/load_role_zones, the bridge from DB rows to policy.py's
pure Person dataclass.

app/nodes/events_sink.py now does real work in frame()/passage() instead of
the Day-4 no-ops: decode, detect every face, embed and recognise each,
dispatch to gate.py or zones.py by node role, and turn the resulting events
into audit_log rows, SSE pushes, and the presence/zone writes above.

Verified live, not only unit-tested. Marin stood in front of gate-in; a real
gate_decision fired through the running server, visible on the SSE stream and
in audit_log a moment later with the correct name and outcome. Three real
pass-sensor trips before he was enrolled correctly produced three
unidentified_passage alerts rather than doing nothing or crashing - proof the
passage-binding path runs correctly against real sensor data. A genuine
sensor-confirmed entry was not captured live in today's session (the pass
sensor was not in reach of where the test happened); the entry path itself is
covered by a dedicated unit test and shares its DB-writing code with
denied_crossed/exit, both of which fired live. Recorded honestly in
docs/REPORT_NOTES.md rather than claimed as fully live-verified. Full test
suite: 62 unit tests plus 2 hardware-free integration smoke tests, all
passing.

## v2-skeleton - 2026-09-03

FastAPI brain skeleton, running end to end against all six live boards rather than
against one as the checkpoint asked for. app/main.py wires together: Database
(runs migrations on startup), aiohttp.ClientSession, SseHub, a NodeRegistry that
loads all enabled nodes from the `nodes` table and starts one supervised poller
per node, and BrainEvents, which is where poller events actually go somewhere -
audit_log rows for online/offline/passage, SSE pushes for the same. Routes:
GET /frame.jpg?node= (served from the poller's cache, not proxied per request -
one open dashboard tab and six do not cost the node six times), GET /nodes (a
full live snapshot: state, online, cam_on, near/pass readings, passages,
restarts), GET /events (SSE, EventSource-friendly, 15s keepalive).

Verified against real hardware, not asserted: all six nodes online within a
second of startup; /frame.jpg?node=gate-in returns a real JPEG (magic bytes
checked) through the running server; /frame.jpg on an unknown node returns 404
cleanly; a live SSE session actually caught a real node flapping and the
matching audit_log rows were there a moment later - the pipeline was exercised
by a genuine event, not a synthetic one.

Added tests/test_registry_smoke.py: a permanent, hardware-free check that the
`nodes` table loads into the correct NodeLive objects (roles, zones, gate
direction), so a future schema or mapping change breaks a test rather than
being noticed live against real boards.

That flapping led to a finding worth recording on its own: one board
(zone-workshop) cycled offline/online roughly every 8-90 seconds while it was
connected to USB for an unrelated MAC read, while the other five boards - on
battery power only - logged exactly one online event each and never flapped
again. Removing the USB cable is being confirmed live; see
docs/REPORT_NOTES.md. Confirmed: after unplugging USB from zone-workshop,
zero offline events in the following 150s, against a prior pattern of roughly
one every 8-90s with USB connected. The practical rule this sets: a board goes
fully to battery before any real test, USB is for flashing only - which
matters for how field recon days are run, not just as a curiosity.

## v3.1-recognition - 2026-09-03

Recognition pipeline: engine, identity tracker, per-person aggregation, enrolment.

app/recognition/engine.py wraps YuNet + SFace, kept deliberately face-agnostic and
threshold-agnostic - detect() returns every face rather than picking "the
largest" (REBUILD_PROMPT §0.6.5: baking that choice into the engine was the old
build's actual tailgating blind spot), and recognise() reports a candidate's raw
score and margin rather than an accept/reject decision, so is_confident_match()
can be a separate, pure function tested with fabricated numbers. Aggregation is
max-over-a-person's-samples, not best-sample-across-the-whole-roster (the old
engine had no per-person step at all, so one lucky enrolment sample could win
outright); margin is the gap to the best OTHER person, never to the winner's
own second-best sample. 11 unit tests, all against synthetic vectors - no
camera, no model files needed to verify the arithmetic.

app/recognition/tracker.py: identity commits only after K consecutive agreeing
frames, and - deliberately - needs no separate "misses before dropping"
parameter, because a miss (no confident match) is just another candidate value
subject to the same K-frame gate. Same two-variable candidate-plus-agreement
shape as the firmware's ultrasonic debounce (pollSonar), reused deliberately.
8 unit tests, including the two that matter most: a single stray miss must not
drop a committed identity, and a different person needs their own full run of
K frames to take over the commitment, not just one lucky frame.

app/db/repositories/{people,embeddings}.py: person CRUD scoped to what
enrolment needs today (not front-loading Day 6/8's access-editing work), and
embedding storage as raw float32 BLOBs stamped with model_version so a future
recogniser swap cannot silently start matching old vectors against new ones.
Round-trip tested against a real temporary database, including that a repeat
enrolment for an existing name adds a sample rather than duplicating the
person.

API: POST /people/enroll?name=&role=&node= (node is REQUIRED - REBUILD_PROMPT
§0.6.4's enrolment-camera-ambiguity bug, and here the equivalent for a frame
with more than one face: refuses rather than guessing which one is the
subject), GET /people, DELETE /people/{id}/samples, and GET
/people/recognise?node= as a tuning readout mirroring the old build's on-screen
"name score" overlay, as JSON instead of pixels.

Verified end to end against a live person (Marin, indoors, incidental
lighting - the real enrolment is Day 10 in the yard per REBUILD_PROMPT §10),
not just unit tests: enrol -> recognise on a genuinely different frame scored
0.625, inside the 0.63-0.93 own-face range this exact camera hardware measured
previously - a real cross-check that alignment/normalisation are wired
correctly. A live tracked sequence showed the confidence gate refuse to commit
on a single lucky frame while the subject moved, and a second sequence showed
it hold a committed identity through two consecutive sub-threshold frames
before recovering - the frame-to-frame jitter behaviour DEMO_ARCHITECTURE §4
describes, caught on real jitter, not asserted. Full sequences in
docs/REPORT_NOTES.md. Test data deleted immediately after; the roster is empty
again.

## v1-firmware - 2026-09-03 (tagged retroactively same-day, on the commit where all six boards were confirmed)

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
