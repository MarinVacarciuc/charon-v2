# Charon/Cerberus — Ground-Up Rebuild Prompt

**How to use this document:** this is the first message of a brand-new chat. The previous
implementation (a single ~950-line Python "brain" script + one admin.html that both grew reactively
over many sessions) accumulated real, repeated classes of bugs and the user is unhappy with the
result. The goal now is a **considered redesign**, not another patch. The physical hardware is
already built and soldered — that part is fixed. Everything above the metal (server architecture,
language, protocols, UI, even whether the Mac is the brain at all) is open for a genuine rethink.

**Ground rules for whoever picks this up:**
1. Read this entire document before proposing any design. It front-loads every hard-won fact so you
   don't waste turns re-deriving things that are already known (pin maps, network quirks, failure
   modes).
2. Do **not** reflash any board or touch the existing repo/code until you have a written plan the
   user has explicitly approved (use plan mode). This is exactly the "jumped into code too fast"
   pattern the user is trying to escape by starting this new chat.
3. Section 0 is non-negotiable ground truth. Sections 1+ describe the *desired* system — treat them
   as requirements to satisfy, not as an existing design to copy line-for-line. You are free to
   invent a different architecture as long as it satisfies the requirements and respects Section 0's
   hard constraints.
4. Work in Russian with the user in chat; code, comments, and commit messages in English. Never add
   Claude/AI attribution to git commits. Verify claims empirically (curl a real endpoint, read a real
   log) rather than asserting something works — this user has caught several confident-but-wrong
   claims already and will check your work.

---

## PHASE 0 — Ground truth (read first, do not re-derive)

### 0.1 What this project is

BTEC HND Digital Technologies (Cyber Security), Unit 21 *Emerging Technologies*. Scenario: **Ezra
and Korede Security Ltd** wants a smart access-control / personnel-safety solution. Deliverables:
a written report (LO1+LO4, ~3000 words, due with the same deadline) and a **live 15-minute
demonstration** (LO2+LO3), deadline **04.10.2026**. One brief criterion is a hard constraint on the
build: **P5 requires a working Arduino Uno + ultrasonic sensor** as part of the minimum viable demo.
An Arduino Uno and 2–3 spare ultrasonic sensors are owned and currently unused — the new architecture
**must** give the Uno a real, legitimate role (not a token add-on). P6 wants evidence of *multiple
iterations* — design the rebuild with visible checkpoints/versioning from day one so that story is
easy to tell honestly in the report, rather than reconstructed after the fact.

Project names: **Charon** (the gate/access-control layer) and **Cerberus** (the interior zone layer)
are locked — keep them. Role/zone model to keep: roles **Guard, Worker, Visitor, Admin, IT**; zones
**Reception, Warehouse, Workshop, Server room**. These are settled narrative choices tied to the
report, not up for renaming debate. *How* they're implemented is fully open.

Staff data is starting **fresh** — do not migrate the old `~/charon-spikes/staff/` embeddings/JSON.
Wipe or ignore it; everyone re-enrols in the new system.

### 0.2 Physical hardware already built — this is fixed, do not redesign

**6× ESP32-S3-WROOM-1 N16R8** boards (confirmed via `esptool flash-id`: 16 MB quad flash, 8 MB
**octal** PSRAM), each with an **OV5640** camera module on a 24-pin FPC ribbon. Build flags that are
confirmed correct for this exact module — use them as-is:

```
FQBN: esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,FlashMode=qio,CDCOnBoot=cdc,PartitionScheme=huge_app
```

`CDCOnBoot=cdc` is required — these boards enumerate as native USB (`/dev/cu.usbmodemXXXX`), not a
UART bridge; without this flag `Serial` output is silently invisible even though upload succeeds.

**Camera pin map — confirmed working on all 6 boards** (this is the `esp32s3-eye` / generic
Freenove-style routing from the Arduino `esp32` core's `camera_pins.h`; a different-brand board of
this camera-connector style can use a *different* map, so don't assume this is universal wisdom — it
is universal *for these specific six boards*, already proven):

| Signal | GPIO | Signal | GPIO |
|---|---|---|---|
| XCLK | 15 | Y9 (D7) | 16 |
| SIOD (SDA) | 4 | Y8 (D6) | 17 |
| SIOC (SCL) | 5 | Y7 (D5) | 18 |
| VSYNC | 6 | Y6 (D4) | 12 |
| HREF | 7 | Y5 (D3) | 10 |
| PCLK | 13 | Y4 (D2) | 8 |
| PWDN | −1 (n/c) | Y3 (D1) | 9 |
| RESET | −1 (n/c) | Y2 (D0) | 11 |

OV5640 has a known cosmetic magenta/purple colour-cast tendency with the esp32-camera driver's
default settings. It does **not** hurt recognition confidence (own-face cosine similarity measured
0.70–0.75 on this exact hardware) — don't burn time "fixing" it unless it becomes a real problem.

**Ultrasonic sensors — RCWL-1601**, deliberately chosen over HC-SR04 because at **3.3 V supply** its
echo output is native **3.3 V logic**, straight into a GPIO, no level-shifter/divider needed (an
HC-SR04 at 5 V would fry a GPIO without one). Already soldered, exact pins **fixed by solder joint**:

| Node | Sensor | Trig | Echo | Meaning |
|---|---|---|---|---|
| all 6 boards | "near" | GPIO 39 | GPIO 38 | "someone is here" — gate: approach/wake trigger; zone: presence |
| gate-in, gate-out **only** | "pass" | GPIO 41 | GPIO 40 | "a body physically crossed the lane" |

The 4 interior/zone boards have **nothing wired to 41/40** — they only ever read the near sensor.
One firmware image can serve all six boards; a zone board's "pass" reading is simply permanent
no-echo. **Two sensors on one board must never fire simultaneously** — they hear each other's echo
and report a phantom distance. They must be time-multiplexed (fire one, wait, fire the other).

**Reserved/forbidden GPIOs on this exact module — do not use for anything else:**
- **4–18**: camera (above)
- **19, 20**: native USB D−/D+ (used for CDC serial — do not repurpose)
- **26–32**: SPI flash
- **33–37**: **octal PSRAM** — this is the camera's frame buffer. Espressif's own docs say these are
  "not recommended for other use" on R8 modules; in practice, touching them can corrupt/crash the
  camera. Treated as absolutely forbidden, not "probably fine."
- **0, 3, 45, 46**: strapping/boot-mode pins — avoid driving these
- **43, 44**: routed to this board variant's onboard USB-UART bridge chip — best avoided even though
  possibly technically free

Free/spare and unused so far: **21, 42, 47, 48**.

**LEDs — designed, wired in firmware, NOT yet physically soldered.** Reserved pins: **GPIO 1 =
green, GPIO 2 = red**, each intended via a ~330 Ω resistor to GND. Currently scoped to the two gate
boards only (could extend to zones). If you build LED feedback, keep these pin assignments; if you
solder them, use these pins.

**Physical board ↔ identity — boards are visually identical, MAC is the only way to tell them
apart** (the user is expected to label them physically, but don't assume it's been done — verify):

| Node id | MAC | Sensors |
|---|---|---|
| gate-in | `28:84:85:9F:C6:20` | near + pass |
| gate-out | `28:84:85:65:6E:24` | near + pass |
| zone-reception | `28:84:85:65:64:5C` | near only |
| zone-warehouse | `28:84:85:9F:C0:EC` | near only |
| zone-workshop | `28:84:85:65:6E:F0` | near only |
| zone-server | `28:84:85:9F:C7:50` | near only |

**Power: 4× 18650 cells in boost-converter power-bank cases.** Confirmed reliable **only** under
continuous moderate/high current draw (camera + WiFi actively streaming). A true low-current
deep-sleep state **trips the boost converter's auto-cutoff** — this bit an earlier prototype and is
a real, repeatable hardware limitation of *this specific* power hardware, not a firmware bug. Any
power-saving design must keep total draw above the cutoff threshold — i.e. **no true deep sleep** on
these packs; lighter idle states (camera paused, WiFi alive) are fine. Measured thermal baseline:
continuous streaming plateaus around **65–68 °C die temperature** (via `temperatureRead()`, the
chip's own junction sensor — measures the die, not the room) — not dangerous, but a legitimate,
measured LO4 energy-efficiency data point if you build an idle/wake feature and want a real
before/after number instead of a guess.

**Arduino Uno + 2–3 ultrasonic sensors**: owned, unused so far. Needs a real role (Section 5).

### 0.3 Network environment — a real hazard, read carefully

- Home network (Virgin Media, band-split router): **`VM6400896_2g`** (2.4 GHz — **this is the one
  that works**, confirmed) and `VM6400896` (5 GHz — ESP32 has no 5 GHz radio, **cannot see it**,
  don't bother listing it as a candidate).
- College network: `GBS-Students` (and a `GBS-Studentss` typo-duplicate seen from the user) —
  expected to have client isolation that blocks node↔brain traffic; never actually validated working
  end-to-end for this reason. Assume it does not work for this system.
- **Demo-day hotspot SSID was never finalised.** This is an open gap you must close before any real
  demo. If you use `WiFiMulti` (joins whichever candidate SSID has the *strongest* signal, not
  whichever is "intended"), a stronger-but-wrong network (e.g. college, if still in the candidate
  list) will silently win over the correct demo hotspot. Either keep the candidate list hygienic
  (only home + demo hotspot, pruned before the demo) or build a mechanism that doesn't have this
  failure mode by construction.
- **mDNS gotcha (real, measured, cost real debugging time):** macOS resolves `*.local` names with
  `AF_UNSPEC` by default. If the ESP32 mDNS responder never answers the AAAA/IPv6 half of that query
  (it doesn't, by default), **every single lookup burns the full 5-second IPv6 timeout** before
  falling back to IPv4. Measured: `AF_UNSPEC` 5.002 s vs explicit `AF_INET` 0.010 s. Whatever language
  the brain ends up in, resolve node hostnames to IPv4 explicitly (and cache the result) — don't let
  the OS default resolver silently eat 5 seconds per camera poll.
- Node naming convention already proven and simple: `<node-id>.local` (`gate-in.local`,
  `zone-server.local`, etc.) via ESPmDNS. No reason to change it unless you have one.

### 0.4 What's already installed on this Mac (same machine, new chat — nothing needs reinstalling)

- `arduino-cli` (via Homebrew) with the `esp32` core (v3.3.8) and `avr` core (for the Uno) already
  downloaded.
- Python venv at `~/charon-spikes/venv` with `opencv-contrib-python` 5.0.0 — gives you
  `cv2.FaceDetectorYN` (YuNet) and `cv2.FaceRecognizerSF` (SFace), no dlib needed. Model files
  (gitignored, large) already downloaded: `face_detection_yunet_2023mar.onnx`,
  `face_recognition_sface_2021dec.onnx`. A tuned similarity threshold of **0.45** (SFace's own
  library default is 0.363) worked well on this hardware — own-face scores 0.63–0.93, typically
  0.70–0.75 through the OV5640 gate camera. Free to keep, retune, or replace the recognition engine
  entirely — this is a real, working, already-tuned reference point either way.
- Ollama (`llama3.2:1b`) and an ElevenLabs integration exist from an earlier voice-persona feature —
  optional, not load-bearing, free to keep/drop/redesign. If keeping any TTS/LLM voice feature: the
  user explicitly asked for a **calm, professional tone**, not a character voice, and for API calls
  to be minimised (cache spoken lines, don't hit a paid API every time). The old ElevenLabs API key
  was pasted directly into a chat at some point — **treat it as compromised, regenerate before real
  use**, same for the OTA password below.
- A Telegram bot (`@CharonGBS_bot`) already exists for phone-side notifications, token at
  `~/charon-spikes/.tg_token` (gitignored) — reusable if you want Telegram as a notification channel,
  or replaceable.

### 0.5 Existing code — reference for facts, not a design to inherit

- Git repo (private): `https://github.com/MarinVacarciuc/charon`, cloned at `~/IdeaProjects/charon`
  (deliberately outside OneDrive — an OneDrive sync/clobber issue bit a sibling project). `.gitignore`
  already excludes secrets, biometric data, and the large ONNX models — keep that discipline.
  `docs/` holds versioned concept-design iterations and a `THREAT_MODEL.md` worth skimming for prior
  security thinking (12 threats → mitigation status) — background, not gospel.
- `firmware/charon_node/charon_node.ino` — the current node firmware. Its **pin mapping, camera-map
  auto-detection, OTA setup, and sensor debounce/hysteresis logic are proven correct** — mine it for
  those facts rather than re-discovering them by trial and error, even if you rewrite the actual
  structure. `firmware/flash_node.sh` and `firmware/ota_node.sh` are working helper scripts (USB
  flash and wireless flash respectively) — reusable regardless of what firmware they push.
- `~/charon-spikes/process_server.py` + `admin.html` + `pip.html` + `board.html` — this is the
  implementation the user is unhappy with. All 6 boards are about to be reflashed anyway, so there is
  **zero continuity burden** — feel free to discard this code wholesale. It is, however, where every
  lesson in Section 0.6 was learned the hard way; read it if you want the "why," but don't copy its
  structure by default.
- **OTA password `CharonGBS2026` was pasted into a chat transcript — rotate it before relying on
  OTA for anything real.**

### 0.6 Hard-won lessons — concrete failure modes already found and fixed once. Don't rediscover these.

1. **mDNS 5-second IPv6 stall** — see 0.3. Resolve IPv4 explicitly, cache it.
2. **Ultrasonic sensors need hysteresis, and even hysteresis isn't always enough.** A single trip
   distance causes noise right at the boundary to flip state repeatedly (6 phantom "passages" in 8
   seconds were measured with no one there). Fix: trip close, only clear once the reading is well
   past the threshold (a ~20 cm gap worked as a starting point). But on a *cluttered test desk*
   (boxes, a wardrobe, a printer nearby), readings were measured swinging chaotically across a
   100+ cm range (13→200 cm frame to frame) — genuine multipath reflection, not simple boundary
   noise. No software filter fully tames that. **Ultrasonic thresholds must be calibrated at the
   final mounted location with a clean sightline, never on a cluttered desk** — the same lesson
   learned calibrating a bin's fill sensor in an earlier project.
3. **Python (or similar) footgun: a variable assigned only after a fallible operation, then read
   inside that same try block's `except`, will throw a *second*, unhandled exception if the first
   one fired before the assignment — and that silently kills whatever thread/task it's running in,
   forever, with no obvious crash log.** Concretely: `v = c["v"]` placed after a network call that
   can raise; the `except` block then reads `v` before it was ever set on that iteration →
   `UnboundLocalError` raised *while already handling* the original exception → thread dies
   permanently → that node just reads "offline" forever with zero indication why. This killed 4 of 6
   camera worker threads in one afternoon and took real debugging time to trace. Whatever you build,
   make sure error-handling paths only ever reference state that is unconditionally available (e.g.
   re-derive from something defined before the `try`, not from something assigned inside it).
4. **Never let a UI or business-logic path implicitly pick "whichever camera currently sees a face"
   as an unnamed default.** This caused two real, separate bugs: (a) a shared video-preview element
   silently swapped between two physically different cameras' footage depending on which one last
   detected a face — looked like the video was glitching; (b) a face-enrolment endpoint captured
   from "whichever camera has a face right now" at click time — a one-frame blink on the intended
   camera plus a stranger walking past a *different* camera could enrol the wrong person's face
   under the operator's chosen name, role, and access rights. **Every camera-specific action must
   name its target camera explicitly. No implicit "primary camera."**
5. **Recognising only the single largest face in frame creates a real blind spot.** A second/third
   person in the same shot is invisible to the decision logic entirely — drawn on screen if you
   bother to visualise it, but never checked, never policy'd. At a gate this is the textbook
   tailgating gap (two people cross together, only one gets a decision, the other enters unrecorded).
   In an interior zone it means a second person's position is simply never updated by that camera.
   Decide deliberately, per context, how multiple simultaneous faces should be handled — don't let
   "biggest face wins" be an accidental default with no thought behind it.
6. **In-memory-only mode flags reset silently on every process restart.** A "require a confirmed
   physical passage before acting" safety mode, if not persisted, quietly reverts to a noisier
   camera-only fallback every time the process restarts — and nothing in the UI necessarily makes
   that obvious. Anything that meaningfully changes system strictness/safety should either persist
   (like the per-node sensor thresholds, which do — stored in NVS on the ESP32 itself) or be made
   impossible to miss in the operator UI.
7. **A "camera-only, no confirmed physical event" mode is inherently chatty.** Recognition confidence
   naturally flickers frame to frame (lighting, motion blur, angle) — near a similarity threshold
   this alone is enough to alternate a spoken "granted"/"unrecognised" announcement rapidly with
   nobody new having arrived. A model where a *decision only commits on a real physical sensor event*
   (not on every camera frame) is dramatically calmer and more correct. Treat "camera-only" as an
   explicitly degraded fallback state, clearly labelled as such — never the default.
8. **Backlighting genuinely wrecks recognition confidence.** A camera aimed toward a bright window
   turns the subject into a silhouette; the resulting face embedding is close to noise, and the
   "best match" bounces almost randomly between enrolled identities frame to frame. Camera
   *placement and orientation* matter as much as any code — this is a physical installation concern
   to design around, not something software can fully compensate for.
9. **A global frame rotation is wrong once cameras can be mounted in different orientations.** The
   old code applied one hard-coded 180° rotation to every camera's frame, inherited from when there
   was only one physical camera. With six independently-mounted cameras, rotation must be a **per-
   node** property, not a global constant.

### 0.7 Open decisions — the new chat should raise these explicitly with the user before locking in an architecture, don't just silently pick one

- **Brain platform: stay on this Mac, or reconsider.** The Mac path is proven and has zero setup
  cost (venv, models, arduino-cli all already installed and working). A phone-as-brain idea was
  explored earlier in this project's history and one specific blocker was found: **Termux/OpenCV on
  a rooted Android phone cannot open that phone's own built-in camera** (no accessible `/dev/video*`
  node) — but this is *not* actually a blocker for "phone as recognition engine" anymore, since the
  camera sources are already the six independent ESP32 nodes streaming over HTTP, not any device's
  local lens. So a phone (or anything else) consuming those same JPEG streams over the network is
  architecturally viable. Surface this trade-off to the user rather than assuming Mac-only.
- **Server language/framework/structure.** The old code was one large Python file using the standard
  library's `ThreadingHTTPServer` and hand-rolled locking. Nothing about the hardware requires
  Python, or a monolith, or polling-based HTTP for status updates (a push mechanism like
  WebSockets/SSE is worth considering for the admin UI instead of the old ~3-4Hz polling loop). Pick
  what best avoids the failure classes in 0.6, and be able to justify the choice.
- **Data storage** for staff/roles/zones/audit — flat JSON+embeddings-on-disk worked but is easy to
  corrupt with concurrent writes; a small embedded DB might be more robust. Open.

---

## PHASE 1 — Node firmware layer

**Goal:** each of the six ESP32-S3 boards is a small, dumb, reliable sensor+camera appliance. All
policy decisions happen in the brain, not on the node.

**Requirements:**
- Serve the current camera frame over HTTP (any reasonable path/format) — proven-good defaults:
  VGA (640×480) JPEG, quality ~12, PSRAM-backed double frame buffer, "grab latest frame" mode (never
  hand the brain a stale queued frame).
- Report the near/pass ultrasonic readings alongside the frame (piggy-backing them on the existing
  frame-fetch response headers, so the brain doesn't need a second request and the node never needs
  to know the brain's — changeable — address, worked well; not mandatory to keep that exact
  mechanism, but the *principle* — node never needs to know the brain's IP — is worth preserving).
- Runtime-configurable, NVS-persisted thresholds for both sensors (a wall-mounted board six-deep in
  a demo room should never need a USB cable to recalibrate).
- Correct hysteresis + multi-reading debounce on both sensors (0.6.2), and correct time-multiplexing
  between the two sensors on a gate board so they never fire simultaneously.
- mDNS advertisement under a stable per-node hostname.
- Password-protected OTA updates (rotate the leaked password — 0.5).
- WiFi candidate list with the network hazard from 0.3 designed around, not just listed and hoped for
  the best.
- A frame-count/face-count-agnostic role: the node reports raw sensor + video data; it does **not**
  run face recognition itself (out of scope for this class of MCU doing it locally at this frame
  rate/quality — recognition belongs on the brain).
- Per-node rotation setting (0.6.9) — do not hard-code one global rotation value anywhere upstream.

**Acceptance:** every node is reachable at `<name>.local`, serves a live frame on request, reports
live sensor distances, survives a WiFi hiccup without needing a power cycle, and can be re-flashed
wirelessly once the very first (necessarily USB) flash has happened.

---

## PHASE 2 — Recognition & presence core (the "brain")

**Goal:** turn six independent video+sensor streams into a coherent, correct model of who is where,
with access decisions that are calm (event-driven, not per-frame-chatty) and honest about their own
blind spots.

**Requirements — multi-camera architecture:**
- An explicit registry of nodes (id, physical role: gate-in/gate-out/zone-X, URL, orientation/
  rotation). **No implicit "primary camera."** Every camera-scoped action (live view, enrolment
  capture, calibration) names its target node explicitly (0.6.4).
- One independent processing path per node — a dead or misbehaving camera must not take down, or
  silently corrupt, any other camera's state (0.6.3's lesson: error paths must be bulletproof against
  the exact footgun described there).
- Recognition engine: YuNet+SFace at threshold ~0.45 is a proven working starting point on this exact
  camera hardware (0.4) — keep, retune, or replace deliberately, not by default drift.

**Requirements — presence & direction model:**
- Direction at the gate is a property of *which physical camera/lane* saw the person (gate-in vs
  gate-out), never a manually-toggled global mode. A manual toggle should exist **only** as an
  explicitly-labelled degraded fallback for the case where only one gate camera is alive.
- A decision (grant/deny/alert, presence flip, token issue/revoke) should commit on a **real,
  sensor-confirmed physical passage**, not on raw per-frame recognition confidence (0.6.7). Camera-
  only commit mode may exist as a fallback but must be visibly, unmissably flagged as degraded
  whenever active — and its on/off state must survive a process restart (0.6.6).
- **Multi-face handling, decided deliberately (0.6.5), not defaulted away:**
  - At the gate: at minimum, flag when more than one face is in view at the moment a passage is
    confirmed (a "possible tailgating" signal), even if you can't identify the second person. Better:
    genuinely evaluate identifying/handling every face in frame, not just the largest, if time
    allows — this closes a real, previously-documented gap in the concept design ("camera count vs
    token count" cross-check) that was never built.
  - In a zone: every recognised, on-site person visible to that camera should have their last-known
    zone updated — not just whichever face is largest. Any unrecognised face inside a zone (zones
    should only ever contain staff who already passed the gate) is a real anomaly worth its own
    alert, independent of how many legitimate faces share the frame — with sensible repeat-alert
    throttling so a lingering stranger doesn't flood the dispatcher.
- Zone authorisation: a person's role/explicit overrides/temporary (just-in-time) grants determine
  which zones they may occupy; being detected in an unauthorised zone is a dispatcher alert, not a
  silent log line.
- Overstay detection (on-site past shift end / max duration), token revocation (admin-forced and
  self-service on exit), audit logging of security-relevant events.
- Heartbeat/liveness per node with a sensible offline timeout, feeding a fail-safe (exit: always let
  people leave) / fail-secure (entry: no confirmed brain = no auto-admit) posture at any physical
  terminal.

**Acceptance:** write this as testable scenarios once the architecture is chosen — e.g. "two people
cross the entry sensor together with only one recognisable face → an alert fires, in addition to
whatever the single recognised person's own outcome was", "a zone camera sees two known staff and one
stranger simultaneously → both staff members' zone updates, exactly one alert fires for the
stranger", "the brain process restarts mid-demo → sensor-confirmed mode is still enforced afterward,
not silently reverted".

---

## PHASE 3 — Interface layer (admin console, gate terminal, on-site board)

**Goal:** design the information architecture *before* writing markup — this was reactive last time
(a dark "control-room" layout, later reorganised into sidebar sections after the user found it
unintuitive) and the user wants a more considered process this time.

**Requirements:**
- A live monitoring view: both gate cameras visible **simultaneously and explicitly labelled**
  (0.6.4 — never one video element that silently swaps footage), plus a genuine multi-camera view for
  the four zone nodes (the old system never got further than four text-only zone columns; a real
  video-tile grid — wake-on-tap, live-when-relevant — was designed conceptually early in this
  project and never built. Consider it.).
- Staff management: enrol (explicitly naming which camera the capture comes from — 0.6.4), edit
  permanent access (role, hours, validity, zones), and just-in-time temporary access grants with
  per-zone independent expiries, revocable from wherever an operator can see where someone currently
  is.
- Settings: every operationally-significant toggle (sensor-confirmed vs camera-only, camera source
  per node, calibration) labelled in plain language with a one-line explanation of what it does —
  the old cryptic single-letter toggles were a specific, named complaint from the user and a redesign
  round already fixed that once; don't regress on it.
- A physical gate terminal screen (phone/tablet/monitor at the door): shows the live decision
  (granted/denied/wait), fail-safe/fail-secure states clearly, and — if you keep a voice feature —
  calm, professional announcements per 0.4's note, not a character voice.
- An audit trail, visible and exportable, for report evidence (LO3 iteration story, LO4 security
  posture).

**Acceptance:** a new operator can look at the Settings page and understand what every control does
without asking; two simultaneous camera feeds are never confusable with each other; an enrolment
action always shows, unambiguously, which physical camera it will capture from before the operator
presses the button.

---

## PHASE 4 — Resilience & security posture

Carry forward the design thinking already documented in `docs/THREAT_MODEL.md` (12 threats →
mitigation status) as background, and build on it rather than starting the threat analysis from zero.
Minimum bar: heartbeat-based node-offline detection feeding real fail-safe/fail-secure terminal
states (0.6 lessons apply); biometric data stored as embeddings, never raw face images, with the
existing `.gitignore` discipline around secrets/biometrics preserved; a clear, honest "what's built
vs what's designed-but-not-built vs what's a documented limitation" split for the report — the old
project was good about this (e.g. "camera count vs token count" tailgating cross-check was
explicitly written up as future work rather than silently ignored) and that honesty is worth keeping
as a house style, not just a one-off.

---

## PHASE 5 — Arduino Uno's role (mandatory, P5)

The Uno + spare ultrasonic sensor(s) currently have no role. The brief requires them in the minimum
viable demo. Prior concept-design thinking (in `docs/` — search for "Heracles") explored the Uno as
an independent backup/watchdog safety path that wakes or acts if the main ESP32/brain system dies —
one legitimate option, not the only one. Whatever role you land on, it must be genuinely functional
and demoable, not soldered on purely for compliance — and the new chat should propose the role and
confirm it with the user rather than assuming.

---

## PHASE 6 — Working style (how the user wants this session to run)

- Communicate with the user in **Russian** in chat; all code, comments, and git artefacts in
  **English**.
- **Never** add Claude/AI co-author attribution to git commits.
- Verify empirically — curl the actual endpoint, read the actual log — before claiming something
  works. This user reads output carefully and has caught confident-but-wrong claims before; state
  what's confirmed vs assumed explicitly.
- Before any destructive or hard-to-reverse action (reflashing a board, overwriting calibration,
  force-pushing, deleting enrolled data) — confirm first. This is especially true right now: don't
  touch the physical boards or the existing repo until the redesign plan itself has been reviewed and
  approved.
- Prefer a small number of real, working, verified pieces over a large amount of unverified,
  simultaneously-built surface area — this is arguably the root cause the user is trying to escape by
  restarting.
