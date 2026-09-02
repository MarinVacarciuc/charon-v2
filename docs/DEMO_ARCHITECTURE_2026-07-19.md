# Charon / Cerberus — Demo-First Architecture (2026-07-19)

Companion to `REBUILD_PROMPT_2026-07-17.md`. That document is hardware ground-truth + hard-won
bug lessons. **This document is the product definition** — what to build, extracted from a detailed
requirements interview with Marin. Read both before designing. Where they overlap, the hardware facts
in the rebuild prompt win; where this defines *behaviour*, this wins.

---

## 0. What we are actually building (the single most important framing)

**Not a turnkey product. A scripted, recorded demonstration.** The deliverable for the Unit 21 viva
(deadline 04.10.2026) is a **video**, composited in post from three recordings:

1. Professional camera footage of Marin walking his backyard (filmed by his daughter / another person).
2. A **screen recording of the laptop dashboard** as it reacts.
3. A screen recording of Marin's phone (showing the token arrive, and wrong-zone notifications).

The examiner watches the edited video. There is **no live real-time performance** in front of the
panel, and every scene can be **re-shot**.

**This changes the whole optimisation target:**
- The **laptop dashboard is THE product.** Build so it reads beautifully and legibly on a screen
  recording, and so each scripted scenario is trivial to stage and re-shoot (including a clean state
  reset between takes).
- Real-time perfection, physical door hardware, and untested robustness are **out of scope** — they
  are report "improvements," not build targets. Do not gold-plate them.
- The system should still be genuinely *correct* on the paths that appear on camera. "Scripted"
  means we control the inputs, not that we fake the outputs.

**The two things that must shine (the "wow", in Marin's own words: "доступ по ролям и паранойя"):**
1. **Role-based zone access** — different real people, genuinely different access. The money shot:
   at the Server room, a **Guard is denied** (alert) while **IT is allowed** (green). Comic relief:
   the **2-year-old son, enrolled as Admin**, walks in with full access.
2. **System paranoia** — anomalies caught **loudly and unambiguously** on the dashboard: unknown face
   at the gate (red, denied); unknown face inside a zone (guard alert); a staff member in a zone
   their role forbids (dashboard alert + that person's phone + a spoken line from the laptop).

---

## 1. The beat sheet (the north star — build exactly what produces this, nothing more)

1. **Gate, arrival.** Marin approaches his real gate. The `gate-in` node's ultrasonic detects him
   (<1.5 m), the camera powers on, the brain recognises him. Dashboard + physical gate LED go
   **green**. The laptop plays a pre-recorded voice line: *"Welcome, Marin."* His phone shows the
   issued token (Telegram).
2. **Pass through.** Dashboard now shows Marin **on-site**.
3. **Reception.** He walks into the passage between the houses (= Reception). That camera wakes,
   recognises him. Dashboard: **Marin is now in Reception.**
4. **Movement.** He walks toward the next zone (shed = Warehouse, swivel = Workshop, grill = Server
   room). On the dashboard he **disappears from the old zone and appears in the new one** — a person
   is in exactly one place at a time. This zone-to-zone movement is the central visual of the video.
5. **The contrast (role wow).** Marin (**Guard**) approaches the Server room (grill). The camera
   recognises him, the brain checks his role → **Guard is forbidden in Server room.** Dashboard
   throws a red alert: *"Marin — Server room — DENIED."* His phone gets a notification. The laptop
   plays: *"Access denied. Server room."* Then **an IT person** approaches the same Server room →
   **allowed → green →** dashboard shows them inside. Same door, two roles, two outcomes, on camera.
6. **The paranoia wow.** A **stranger** (someone not enrolled) approaches the gate → **red frame,
   denied.** A stranger appears in a zone → **guard-dashboard alert: "unknown person in [zone]."**
7. **The P5 climax (Arduino).** Marin **kills the smart gate** — unplugs the gate ESP / cuts its
   WiFi. Dashboard: **gate node offline.** He walks up anyway. The **Arduino Uno at the gate —
   completely independent, no network, no laptop — detects the smart system is gone and lights its
   own green LED: the gate still passes people.** Narration: *graceful degradation — even when every
   smart component fails, the perimeter does not.*

Everything in this document exists to make these seven beats produce cleanly and re-shoot easily.

---

## 2. System layers (three, deliberately)

- **Layer 1 — Nodes (6× ESP32-S3):** dumb sensor + camera appliances. Serve frames, report sensor
  distances, keep the camera powered off until someone approaches. **No face recognition on the
  node** (out of reach for this MCU at useful quality/rate — recognition is the brain's job).
- **Layer 2 — Brain (laptop):** consumes the six streams, runs recognition, owns the single source
  of truth for *who is where*, makes every access decision, drives the dashboard, plays the voice.
- **Layer 3 — Failover (Arduino Uno at the gate):** an independent, dumb, unkillable watchdog that
  physically takes over the gate when Layer 2 or the gate node dies.

The point is that Layers 2 and 3 are **two brains of deliberately different intelligence** — a smart
one and a dumb-but-unkillable one — which is the report's defense-in-depth / graceful-degradation
story made literal.

---

## 3. Node firmware behaviour (Layer 1)

- **Camera OFF by default.** Near-sensor (GPIO 39/38) trip <1.5 m → **camera ON**, start serving
  frames; person leaves → camera OFF after a short timeout. **WiFi stays on always** (keeps the node
  reachable/manageable, and keeps the 18650 boost-bank above its low-current auto-cutoff — confirmed
  the bank does not drop with camera-off/WiFi-alive). This is the energy-efficiency + privacy-by-
  design story for LO4: cameras don't record until someone is actually there.
  - Wake latency is ~1 s (camera re-init). Fine for zones — you walk up and pause. Do **not** rely
    on it for a fast walk-through; Marin dwells at each zone.
- Report near (and, on gate nodes, pass) sensor distances alongside the frame (piggy-back on the
  frame response headers — the node must never need to know the brain's changing address).
- **Gate nodes only:** pulse a **heartbeat GPIO** (~1 Hz) while the node is healthy **and** its last
  contact with the brain is recent — this single wire is what the Arduino watches (see §8). Losing
  WiFi, crashing, or the brain dying all collapse the heartbeat.
- Carry forward unchanged from the rebuild prompt: proven camera pin map, mDNS `<node>.local`,
  password-protected OTA (**rotate the leaked password first**), per-node rotation, NVS-persisted
  sensor thresholds, hysteresis + two-reading debounce, and time-multiplexed firing of the two
  gate sensors.

---

## 4. Recognition & presence model (Layer 2 core loop)

- **One current location per person.** Whenever a node confidently recognises someone, that person's
  location becomes that node's zone. They are in exactly one place — the **last** zone that
  recognised them. Moving = that value changing; the old zone is simply vacated.
- **Dwell / debounce (~2 s):** require a person to be seen for a moment before committing a zone
  change, so walking *past* a sensor in transit does not flicker them through zones. This keeps the
  board clean, which matters because the board is on camera.
- **Presence is recognition-driven, not passage-sensor-driven.** Because the demo is scripted, there
  are no false physical events to defend against, so the whole "commit only on a confirmed passage"
  machinery from the old build is **dropped**. The gate pass-sensor (41/40) remains a bonus signal,
  not load-bearing.
- **Confidence gating:** require a few consecutive agreeing frames (same identity, adequate
  similarity ~0.45+) before committing an identity. This kills the frame-to-frame jitter bug class.
  No confident match → treat as **unknown**. The system refuses to name someone it isn't sure of,
  rather than guessing.
- **Multiple faces in one frame:**
  - **Zone:** evaluate **every** detected face. Each recognised, on-site person → their zone updates.
    **Any** unrecognised face → a guard alert (throttled so a lingering stranger doesn't flood the
    feed). A zone should only contain staff who passed the gate, so an unknown face inside is a real
    anomaly on its own merit.
  - **Gate:** act on the largest face for the grant; flag >1 face as *possible tailgating* — but this
    is **report-only**, never staged in the video (Marin won't create it; production uses a
    turnstile).

---

## 5. Access decisions & paranoia rules (Layer 2)

- **Role → allowed zones** (matrix in §11). A person recognised in a zone their role forbids →
  **alert**: dashboard (loud, red, named) + that person's phone (Telegram) + a pre-recorded voice
  line from the laptop.
- **Unknown at the gate** → red / deny. **Unknown in a zone** → guard-dashboard alert.
- **JIT temporary grant (INCLUDED — a headline beat).** Admin grants e.g. IT a 15-minute Workshop
  pass on request; IT enters a normally-forbidden zone; the grant **expires by itself** (no manual
  revert — solves privilege creep). Strong LO1/LO4: the direct real-world parallel to cloud temporary
  credentials / just-in-time privilege elevation, and a great "strict but flexible" beat on camera.
  **The current build implements this flawlessly** (per-zone grants, each with its own independent
  expiry, auto-ignored once past) — treat that behaviour as the reference to preserve, not to
  reinvent worse. Keep: per-zone independent expiries, "grant all filled", "clear all temporary",
  and the audit line on every grant.
- **Time-window access (INCLUDED).** A role/person may be allowed a zone only within an hours window
  (e.g. a **Cleaner**: all zones, but only 18:00–20:00). Arriving off-hours → denied. Demonstrates
  the system checks **when**, not only **who**. Also already present in the current build (the
  `hours_from`/`hours_to` + `valid_until` policy check) — carry the behaviour forward.
- **Optional (build only if Marin opts in): Overstay** — on-site past shift end → gentle nudge →
  alert.

---

## 6. The dashboard (Layer 2 — the star of the recording)

- **Keep the current "On-site by zone" column board** (Marin's explicit pick; the spatial yard-map is
  a report "improvement", not built now). Within it, make **movement crisp**: on a zone change, the
  person's card visibly leaves the old column and highlights in the new one.
- **Anomaly feed must be loud and unmissable** — wrong-zone and unknown events render big and red
  with name + zone + reason. This *is* the visible "paranoia."
- **Three distinct camera states**, never confusable: **online** (live), **asleep** (dark, "armed" —
  camera off, waiting for approach), **offline / possible sabotage** (alarm). A sleeping camera must
  never look like a dead one.
- **Gate:** two live tiles, each explicitly labelled (`ENTRY · gate-in`, `EXIT · gate-out`) — never
  one tile that silently swaps footage between two physical cameras.
- **A clean state-reset control** ("clear all presence / reset take") — essential for re-shooting.

---

## 7. Voice (Layer 2)

- **Pre-generated AI-voice files**, calm and professional (no character voice, no live LLM, no
  runtime API). Two families of line, generated once and saved:
  - **Gate welcome, per enrolled person** — *"Welcome, Marin."*
  - **Wrong-zone denial** — *"Access denied. Server room."*
- The laptop plays the matching file on the matching event. Because the cast and script are known in
  advance, the exact finite set of needed lines can be pre-baked before the shoot.

---

## 8. Arduino failover (Layer 3 — satisfies P5)

- **Wiring:** gate ESP heartbeat GPIO → an Arduino Uno input pin, **plus a shared ground** (power
  both the ESP and the Uno from the **same** gate powerbank so ground is common — a 2-port bank or a
  USB splitter; verify the bank supplies both). The ESP pin is 3.3 V into the Uno's 5 V-tolerant
  input — safe, one-directional; never wire the reverse.
- The Uno has **its own ultrasonic + red/green LEDs** (and, if available, a buzzer — the brief asks
  for an "alarm", a buzzer strengthens the P5 claim).
- **Heartbeat present** → Uno passive (dark, or a dim "armed" indicator).
- **Heartbeat lost ~3 s** (ESP dead, WiFi lost, or brain dead — all collapse it) → **Uno owns the
  gate**: its ultrasonic detects approach → **green LED → "open."** This is **presence-based** — the
  Uno cannot recognise faces, which is the honest limitation.
- **Demo behaviour = the dramatic beat above (open on presence when offline).**
- **Report improvements (not built):** (a) the security-correct *fail-secure* posture — offline entry
  should hold ("see the guard") while exit stays always-open per fire-egress law (BS 7273-4); (b)
  Marin's idea — a **redundant server at the gate carrying its own cached face database**, which in
  production would take over *identity-aware* access when the primary brain/network dies, instead of
  the Uno's dumb open-on-presence.

---

## 9. Data & configuration

- **Fresh staff database — no migration** from the old `~/charon-spikes/staff/`.
- **Config as data, not code:** nodes (id, physical role, zone, url, rotation), zones, the role→zone
  matrix, thresholds — all declarative, so adding/moving a camera is an edit, not a code change in
  three places.
- Store face **embeddings, never raw images** (GDPR). Preserve the existing `.gitignore` discipline
  (secrets + biometrics never committed).

---

## 10. Physical shoot — risks & pre-shoot dry-run checklist

- **Hotspot = a separate phone placed centrally**, in WiFi range of all six nodes **and** the roaming
  laptop throughout the walk. **This is the #1 risk to the shoot.** Dry-run the full path — gate →
  passage → shed → swivel → grill — watching all six nodes stay online, **before** filming for real.
- **Enrollment photos taken in the same yard, same light, multiple angles and spots** as the shoot —
  Marin's own mitigation, and the single biggest recognition win. Do this properly.
- **Lighting:** shoot in even, diffuse light (overcast or open shade). Avoid any camera aimed into
  direct sun or a bright sky — backlighting turns a face into a silhouette and was a proven
  recognition killer.
- **Gate powerbank now feeds ESP + Arduino** — confirm it supplies both under load.
- **Sleeping-camera power** confirmed safe (WiFi keeps the bank above cutoff) — but re-verify on the
  actual packs used for the shoot.

---

## 11. Role → zone matrix (locked)

| Role | Allowed zones | Time window |
|---|---|---|
| Admin | all (Reception, Warehouse, Workshop, Server room) | any |
| Guard | Reception, Warehouse, Workshop | any |
| Worker | Reception, Warehouse, Workshop | any |
| IT | Reception, Server room | any |
| Visitor | Reception | any |
| Cleaner | all | 18:00–20:00 only |

Plus **just-in-time temporary grants** on top of the base role (per-zone, independent expiry,
auto-lapsing) — e.g. IT gets a 15-minute Workshop pass. This is a headline demo beat, not an extra.

Demo cast (default — Marin to confirm/adjust): Marin = **Guard** (the hero who hits the Server-room
wall), spouse = **IT** (the green-light contrast at the Server room), 2-year-old son = **Admin** (the
gag), one more person = **Visitor** (the most-restricted role), plus an un-enrolled **stranger**.

---

## 12. Explicitly NOT built now — report as "improvements / future work"

- Physical door / lock / servo; per-zone sirens; guard-call button.
- Live tailgating detection (production uses a turnstile).
- Camera-sabotage alerting as a *staged* beat (dashboard heartbeat exists; not filmed).
- Redundant gate server with its own face DB; PIN/RFID offline credential; per-zone Bluetooth
  speakers; the spatial top-down yard map.

These are not failures — writing them up honestly as designed-but-not-built is a deliberate house
style and reads as maturity, not as gaps.

---

## 13. Open decision for the top of the build session

Build in **this** chat, or in a **fresh** chat seeded with this document + the rebuild prompt? Either
works; the two docs together are a complete brief. If a fresh chat: start it in **plan mode**, have
it read `REBUILD_PROMPT_2026-07-17.md` and this file first, and approve a written plan before any
code or any board is touched — that discipline is exactly what this restart is for.
