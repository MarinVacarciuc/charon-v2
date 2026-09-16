# Report notes

Running evidence for the Unit 21 report (LO1 + LO4), written as decisions are made rather
than reconstructed afterwards. The report itself is a separate piece of work; this file
exists so that nothing has to be remembered.

Three buckets, kept honestly separate, matching the house style the earlier project used:
**built** (exists and was tested), **designed, not built** (thought through, deliberately
out of scope), **documented limitation** (a real weakness that is being lived with).

Citations are marked `[CITE: ...]` where the report will need a real reference. They are
deliberately not filled in with plausible-looking sources here.

---

## Decisions with a security trade-off

### OTA firmware updates are unauthenticated

**Status: documented limitation.** Decided 2026-09-02.

Wireless firmware updates use `ArduinoOTA` with no password. Anyone with access to the
network the nodes are on can push a new image to any of them.

*Why it is acceptable here.* The six nodes only ever run on a private phone hotspot for
the demonstration, or the home network for bench work. Neither is a shared or hostile
network, and the exposure window is a two-week build plus a filming session.

*Why the password was removed rather than never added.* The build initially carried a
shared OTA password, rotated on 2026-09-02 because the previous value had been exposed.
The password creates its own availability hazard: it is compiled into the image, so it has
to stay in sync between `secrets.h` and whatever is already on each board. A mismatch does
not fail gracefully - it locks that board out of wireless updates entirely and forces it to
be taken off its mounting for a USB flash. With six wall-mounted boards and a fourteen-day
schedule, that failure mode costs more than the threat it defends against.

*What production would do instead.* Authenticated OTA is the minimum, and signed firmware
images are the real answer: a password only proves the uploader knows a secret, while a
signature proves the *image* came from the right place, which is the property that actually
defends against a supply-chain or rogue-update attack. `[CITE: firmware update security /
secure boot guidance - NIST SP 800-193 or equivalent]`

*How it maps to the existing threat model.* This is threat **C4** (firmware supply chain),
which was already recorded as *planned* rather than implemented. This entry sharpens it
from "not done yet" to "consciously declined, with the reasoning".

---

## Design decisions worth explaining

### The demo network is preferred by position, not by signal strength

**Status: built.** 2026-09-02.

`WiFiMulti` joins whichever candidate network is *strongest*, which is not the same as the
one that is *correct*. On shoot day, a house router closer to the gate than the phone
hotspot would pull some boards onto the home network while others joined the hotspot, and
the laptop can only be on one of them. Half the nodes would read OFFLINE with nothing on
screen explaining why.

The firmware now treats `CHARON_APS[0]` as a preferred network and joins it explicitly by
name first, falling back to `WiFiMulti` only if it is unavailable, and moving back to it if
it reappears. The node also reports its joined SSID in `/status`, so being on the wrong
network is visible on the dashboard rather than silent.

This is an example of removing a failure mode *by construction* rather than by procedure
(the alternative was "remember to prune the candidate list before filming").

### Cameras are off until someone is present

**Status: built and validated on hardware 2026-09-02, soak-tested 2026-09-03, then
deliberately replaced on 2026-09-13.** Both versions matter to the report, and the reason
for the change is the interesting part.

**What was built.** Each node kept its camera powered down and initialised it only when the
ultrasonic near sensor reported someone within 250 cm, sleeping again after 20 s idle. WiFi
stayed up throughout, which is also a power requirement: a true deep sleep drops the current
draw below the 18650 boost-converter bank's auto-cutoff and the pack switches itself off.
That is a measured property of this specific power hardware, not a firmware bug. The
108-cycle bench soak passed with no failures, no reboot and no heap leak (see Measurements),
so the design was sound and the energy claim was measured rather than asserted.

**Why it was replaced.** The soak also measured the cost: **median 937 ms from wake to first
usable frame**. That second is spent exactly when the frames matter, while the subject is
still walking in, so the earliest frames the brain received were of a face at an angle and in
motion. The 250 cm trip distance existed only to buy back that second of warm-up. It was
solving a problem the design had itself created.

**What replaced it.** The camera now initialises at boot and stays initialised. The near
sensor no longer switches anything on; it reports *recognition range*, set to **100 cm**, and
the brain pulls frames only while somebody is inside that range or an operator has explicitly
asked for a look. One metre is where an approaching person is square-on to the camera and
still moving slowly enough to yield a usable frame.

**The privacy argument survives the change, and moves up a layer.** Data minimisation was
never really a property of the camera being unpowered; it is a property of nothing being
captured, processed or stored when the doorway is empty. That is still true, and it is now
enforced by the brain declining to request a frame rather than by the sensor cutting power.
The honest qualification for the report is that enforcement in software is weaker than
enforcement in hardware: a defect in the brain could request frames it should not, whereas an
unpowered camera physically cannot produce one. That trade, a stronger guarantee exchanged
for a system that identifies people accurately enough to be worth deploying, is exactly the
kind of decision LO4 asks to be defended rather than glossed.
`[CITE: data minimisation / privacy by design - UK GDPR Art. 5(1)(c) and Art. 25]`

**Cost accepted.** Holding the camera on costs ~23 400 B of internal heap per node
permanently (measured, see Measurements) and removes the idle-power saving. Both were judged
worth paying for recognition that works on the first frame instead of the fifth.

---

## Measurements to date

### Camera wake/sleep soak, gate-in, 2026-09-03

The camera-off-by-design decision was gated on this, because a leaky or fragile
`esp_camera_init` / `esp_camera_deinit` cycle would present as a board that quietly stops
serving frames hours into a shoot. Run with `server/tools/camera_soak.py` against the real
board over WiFi.

| Quantity | Result |
|---|---|
| Cycles | 108 (100 wake/sleep, 8 wake/frame/sleep) |
| Failures | 0 |
| Board reboots | 0 (uptime rose 14 s to 378 s unbroken) |
| Free heap, camera asleep | 195 632 B first, 196 168 B last |
| Heap drift | **+536 B over 108 cycles (+5.0 B/cycle)** - no leak; positive drift is allocator noise |
| Free heap, camera awake | ~172 800 B |
| Cost of holding the camera on | **~23 400 B of internal heap** (frame buffers themselves sit in PSRAM) |
| Die temperature | 63.6 to 66.6 C |
| Wake plus first frame | median 937 ms (872 to 989) |
| Frame size, VGA quality 12 | median 9 907 B (9 634 to 12 364) |

The ~1 s wake was the reason the near sensor woke the camera rather than the first frame
request: at a walking pace, 2.5 m of approach is about the margin needed for the camera to
be ready by the time a face is in frame.

**Superseded 2026-09-13.** This measurement is what argued the sleeping design out of the
build. Rather than keep spending 937 ms of every approach on warm-up, and keep the trip
distance at 2.5 m purely to hide it, the camera now stays initialised and the sensor reports
recognition range at 1 m instead. The figures above stand as the measurement of the design
that was replaced, and the ~23 400 B heap cost of holding the camera on is now paid
permanently on every node.

Verdict: **ships as designed.** The fallback of keeping the camera initialised while idle is
not needed.

### mDNS resolution, 2026-09-03

Measured with `server/tools/measure_dns.py` against the live node.

| Resolution | Median | Min | Max |
|---|---|---|---|
| `AF_UNSPEC` (the OS default) | 35 002 ms | 5 011 ms | 35 013 ms |
| `AF_INET` (what the brain uses) | 0.8 ms | 0.7 ms | 1.1 ms |

The 5 011 ms floor reproduces the previously documented 5.002 s exactly: macOS asks for both
A and AAAA records, the ESP32 answers the A half and never answers the AAAA half, and the
resolver waits out the full IPv6 timeout every time. The much worse median was measured
while the board was under load from the soak test, when some mDNS responses were dropped and
the timeout was paid several times over. That is the honest worst case, and it is the
condition the system actually runs in.

Presented as OFFLINE nodes rather than as slow ones, which is what made it expensive to
diagnose the first time. `app/nodes/resolver.py` forces `AF_INET`, caches for 60 s, and
connects by literal IP so no resolver runs on the request path at all.

### Demo hotspot: peer-to-peer UDP does not pass, TCP does, 2026-09-03

**Status: documented limitation, confirmed on the actual phone hotspot (`charon`).**

Firmware OTA updates (`ota_node.sh`, `ArduinoOTA`) use a UDP request/response handshake on
port 3232 before the actual image transfers over TCP. Over the demo hotspot, that UDP
handshake gets no response from the board, every time, from both a freshly booted board and
one that had been running for a while - ruling out stale state as the cause. Every other path
the system depends on at runtime (`/status`, `/shot.jpg`, `/threshold`, `/led`, `/wake`) is
plain HTTP over TCP and was confirmed working reliably over the same hotspot, to all six
boards, in the same session.

Ruled out before concluding this is the hotspot itself: the Mac's application firewall is
disabled; routing to the 10.166.30.0/24 hotspot subnet goes directly over the WiFi interface
with no VPN tunnel involved (checked via the routing table); ARP had already resolved all six
boards' MAC addresses, confirming Layer 2 connectivity; and the `auth_upload=no` TXT record
correctly advertised over mDNS, so authentication was not the blocker either.

The remaining explanation is a known limitation of phone-based personal hotspots: many
implement each connected device closer to a separate NAT client than a true bridged network,
which tends to handle a straightforward client-initiated TCP flow (what HTTP polling is)
far more reliably than a connectionless UDP request that has to be routed client-to-client
through the phone rather than client-to-internet. `[CITE: mobile hotspot NAT / client
isolation behaviour - a vendor or Android/iOS networking source, not yet identified]`

*Practical consequence:* OTA firmware updates are not relied on for the demo hotspot. USB
flashing, already proven on all six boards, is the fallback and remains the primary path for
any firmware change made in the yard. This does **not** affect in-place recalibration
(`/threshold?cm=&wake=`), which is plain HTTP and was exercised successfully on multiple
boards. This is exactly the risk `REBUILD_PROMPT` §0.3 and `DEMO_ARCHITECTURE` §10 flagged as
the single biggest hazard to the shoot ("the demo hotspot SSID was never finalised" /
"this is the #1 risk to the shoot") - now measured rather than merely anticipated.

### Fleet-wide load on the demo hotspot, 2026-09-03

All six boards were live simultaneously for the first time, on battery power, on `charon`,
with the Mac also on the hotspot. Six requests per round, five rounds, back to back:

| Node | Median | Max | Failures |
|---|---|---|---|
| gate-in | 75 ms | 148 ms | 0/5 |
| gate-out | 21 ms | 2144 ms | 0/5 |
| zone-reception | 81 ms | 225 ms | 0/5 |
| zone-warehouse | 296 ms | 867 ms | 0/5 |
| zone-workshop | 619 ms | 1147 ms | 0/5 |
| zone-server | 26 ms | 41 ms | 0/5 |

Zero outright failures, but latency is markedly worse and far less even than a single board
polled in isolation (20-67 ms, measured earlier the same day). Die temperature was also
elevated across the fleet: 65.5-80.6 C, against the 63.6-66.6 C measured on one board cycling
normally. Both effects trace to the same cause, confirmed by the near-sensor readings at the
time (3.9-85.9 cm on every board): the boards were physically clustered on a bench, each
one's near sensor was tripped by the others' proximity or general clutter, and all six
cameras were awake and streaming simultaneously - six radios contending for airtime on one
2.4 GHz channel, worst case, rather than the one-or-two-awake-at-a-time pattern the
camera-off-by-default design targets. This is a real number worth keeping (LO4: it is the
honest worst case for airtime contention), but it is a bench artifact, not the expected
running condition once the boards are spread across the yard per their actual mounting
positions - the fix is physical separation, which was always the plan, not a software change.
The brain's 1.5 s status timeout was sized against the isolated-board measurement; it holds
under this clustered worst case too (zero failures), so no change is needed on that evidence.

*Still valid after the 2026-09-13 camera change.* What contended for airtime here was six
boards **streaming**, not six cameras being powered, and streaming is still gated: the brain
requests frames only from nodes with somebody inside recognition range. If anything the
clustered worst case is now harder to reach by accident, because the trip distance dropped
from 250 cm to 100 cm, so boards sitting near each other on a bench are less likely to hold
each other's sensors tripped.

### Node polling and failure detection, 2026-09-03

Measured against the live `gate-out` board and, for the failure case, against a LAN address
with nothing listening (which is what an unplugged board looks like from the brain).

| Quantity | Value |
|---|---|
| `/status` response | median 20 ms, p95 35 ms, max 67 ms (n=40) |
| `/shot.jpg` response, camera already awake | median 41 ms, max 61 ms (n=8) |
| Frames delivered from one awake node | ~1.7 per second at a 3 Hz poll |
| Time to declare a dead node OFFLINE | **6.3 s** (was 8.0 s before splitting the timeouts) |

The request timeout was originally one value for both endpoints. Splitting it matters
because how quickly a dead board is noticed is bounded by the timeout on the cheap endpoint:
`/status` touches no hardware, so 1.5 s is a twentyfold margin over its worst measured
response while still failing fast, whereas `/shot.jpg` may have to power the camera up first
and needs seconds. Detection is now bounded by the 6 s grace period itself, which exists so
that one dropped poll on a phone hotspot does not raise a security event.

A second finding from the same test: resolving a `.local` name that nobody answers costs the
full mDNS timeout, so a node that had just died was only being retried every ~2.7 s. The
poller now keeps hitting the last known address while a node is down - a TCP connection to a
dead host fails in milliseconds - and only re-resolves after ten consecutive failures, which
is the case where the node genuinely moved to a new address.

Fault isolation was verified rather than assumed: with one board live and one unpowered, the
live node kept delivering frames with zero errors while the dead one sat OFFLINE. That is
the property the per-node supervisor exists to guarantee, and the previous build did not
have it - four of six camera workers died silently in one afternoon.

### Ultrasonic behaviour on a bench, 2026-09-03

Near-sensor readings on a cluttered desk swung between 33 cm and 233 cm frame to frame with
nothing moving. This is multipath, not sensor noise, and no software filter fixes it: it is
why thresholds are calibrated at the final mounted position and why the PASS sensor counted
phantom passages while the board sat on a desk. The two-reading debounce was observed
rejecting single stray samples correctly (a lone 54 cm reading did not flip the state).

### Toolchain and startup



| Quantity | Value | How measured | Date |
|---|---|---|---|
| YuNet model load | 0.054 s | Python timing, OpenCV 5.0.0.93 | 2026-09-02 |
| SFace model load | 0.147 s | same | 2026-09-02 |
| Both models load from `server/models/` | 0.21 s | same, on Python 3.12.14 | 2026-09-02 |
| YuNet detect, 640x480 blank frame | 9.7 ms average over 20 runs | same | 2026-09-02 |
| Node firmware v2 size | 1 164 331 B, 37% of partition | `arduino-cli compile` | 2026-09-02 |
| Node firmware v2 static RAM | 63 088 B, 19% | same | 2026-09-02 |

Carried forward from the earlier project, to be re-measured on this build rather than
quoted second-hand:

| Quantity | Previously measured | Status |
|---|---|---|
| mDNS lookup, `AF_UNSPEC` vs `AF_INET` | 5.002 s vs 0.010 s | **re-measured, see above** |
| Own-face cosine similarity through the OV5640 | 0.63 to 0.93, typically 0.70 to 0.75 | to re-measure after re-enrolment |
| Continuous-streaming die temperature | 65 to 68 C | **re-measured: 63.6-66.6 C under wake/sleep cycling** |
| Phantom passages without hysteresis | 6 in 8 s with nobody present | already fixed; cite as the reason hysteresis exists |
| Ultrasonic multipath on a cluttered desk | 13 to 200 cm frame to frame | **reproduced: 33-233 cm, see above** |

### Recognition pipeline, end to end against a live person, 2026-09-03

**Status: built and verified live, not just unit-tested.** Marin stood in front of gate-in
(indoors, incidental lighting, rain having postponed the real field recon) for a real
enrol-then-recognise round trip through the running server, not a synthetic test.

One sample enrolled (`POST /people/enroll`, detection score 0.862). Recognising a genuinely
different frame moments later, not the enrolment frame itself, scored **0.625** - inside the
0.63-0.93 own-face range this exact camera hardware measured in the previous build
(REBUILD_PROMPT §0.4), which is a strong cross-check that alignment and normalisation are
wired correctly, not just "some number came back."

With only one enrolled sample, a first tracked sequence showed the fragility a single angle
has to pose change: of 6 frames as the subject moved, only 1 cleared the confidence gate, and
`IdentityTracker` correctly refused to commit on that lone hit - exactly the discipline it
exists to enforce, and a concrete argument for REBUILD_PROMPT §10's "several angles and
lightings" during real enrolment, not just received wisdom.

A second sequence, subject holding still, is the cleanest demonstration of the whole design
working as one:

| Frame | Raw match | Score | Committed |
|---|---|---|---|
| 1 | RainTest | 0.769 | - |
| 2 | RainTest | 0.761 | - |
| 3 | RainTest | 0.809 | **RainTest** (3rd consecutive frame) |
| 4 | RainTest | 0.552 | RainTest |
| 5 | none (0.424 - below the 0.45 threshold) | 0.424 | **RainTest** (held) |
| 6 | none (0.419) | 0.419 | **RainTest** (held) |
| 7 | RainTest | 0.608 | RainTest |
| 8 | RainTest | 0.582 | RainTest |

Frames 5-6 are the finding: two consecutive sub-threshold readings, and the tracker did not
drop the identity, exactly the sticky-hysteresis behaviour it was designed for (see
app/recognition/tracker.py) and exactly what DEMO_ARCHITECTURE §4 calls "kills the
frame-to-frame jitter bug class" - caught here on a real person's real jitter, not asserted.

Test data (person "RainTest" and its embedding) deleted immediately after - this was a
pipeline check, not real roster data. Real enrolment is Day 10, in the yard, in the actual
shoot lighting, per REBUILD_PROMPT §10's own lesson.

### RFID as the failover credential, 2026-09-07

**Status: built in firmware, pending wiring.** Marin's idea, and it fixes a weakness this
project had already written down as a limitation rather than solved.

The first failover design opened the gate on **presence alone**: while the smart path was
down, anyone who walked up got in. That is a poor thing to present as a security feature, and
it quietly contradicts the fail-secure posture the brief asks for on an entry lane
(REBUILD_PROMPT B2). A card now opens the gate, and the ultrasonic keeps a different and
better job: noticing that somebody approached, so an approach with **no card presented** is
recorded (`NO_CARD`) instead of being silently rewarded with an open gate.

The layering is the textbook one and is worth stating in exactly these terms: the primary
factor is *something you are* (face), the failover is *something you have* (card). Degrading
from one to the other loses convenience and loses the ability to tell people apart by
appearance - it does **not** lose the ability to say no. That is the property that makes it a
graceful degradation rather than a bypass.

Costs, stated rather than buried:

* **A card is clonable.** Anyone who learns a UID can write it to a blank card. That is the
  generic weakness of a possession factor, and it is why the UIDs live in a gitignored
  `cards.h` beside `secrets.h` rather than in the repository.
* **Entry by card during an outage is invisible to the brain until somebody collects the
  journal.** Solved 2026-09-07, and the shape of the solution is the interesting part. Marin
  first suggested an SD card in the gate ESP32; that would have recorded nothing, because the
  card reader is on the *Uno*, and the ESP32 is both on the far side of a one-way wire and the
  thing being killed in the demo's own scenario. The data was on the wrong side of the gap.
  The Uno instead keeps a 113-record journal in its own EEPROM - no extra hardware, no extra
  pins - and hands it over on request (`D` over serial), which `tools/import_uno_log.py` folds
  into `audit_log` with the offsets anchored to real time.

  The ring buffer overwrites the oldest records when full, at Marin's call and correctly:
  reconciliation is about the outage happening now, and older sessions are noise. The dump
  always reports that wrapping occurred, so a full journal is never read as a complete one.

  What remains designed-not-built is *automatic* delivery, and deliberately so: the Uno has no
  network, and giving it one through the ESP32 would reintroduce the dependency the whole
  layer exists to avoid. A genuinely independent backstop cannot report on itself - somebody
  has to go and collect it. That is a property of independence, not a gap in the build.
* **If the reader fails, nobody gets in during an outage.** For an entry lane that is the
  correct posture, and it is more correct than what it replaced.

The board still stays inert while the brain is alive - the reader is not even polled. Two
systems deciding one gate is worse than either alone.

Incidentally this improves the last beat on camera: "the smart path died and the perimeter
still checks credentials" is a better thing to film than someone walking up to a gate that
opens for anybody, and tapping a card is a deliberate, legible action in a way that walking
forward is not.

### Pre-shoot adversarial review: seven defects found and fixed, 2026-09-11

**Status: all seven fixed, with regression tests.** Worth recording as much for how the review
behaved as for what it found.

**The review itself failed twice.** A multi-agent adversarial pass was run on 2026-09-07 (five
reviewers, one skeptic per finding - 70 agents) and hit a session limit with 61 of 70 agents
dead. A leaner re-run on 2026-09-10 (five reviewers, one skeptic per dimension - 10 agents)
hit the limit again, completing 3 of 8. Its summary read "18 raised, 18 refuted", which was an
artifact of the script counting an unverified finding as unconfirmed: they were not refuted,
they were never examined. Worth naming, because a review that reports zero findings because it
died is indistinguishable from one that reports zero findings because the code is clean.

The 18 findings were then verified by hand against the code. Three were raised independently
by two different reviewers, which turned out to be a good signal - all three were real.

| # | Defect | Consequence |
|---|---|---|
| 1 | Shared cv2 DNN objects called from six executor threads | crash or corrupted detection mid-take |
| 2 | Policy compared local-meaning hours against a UTC clock | every window an hour out |
| 3 | `denied_crossed` never consumed the pending decision | alert storm, repeated token issue |
| 4 | Entry did not clear `at_zone_id`; zones written for off-site people | beat 3 pre-empted |
| 5 | An empty hours field raised into an endless restart loop | one cleared field kills a node |
| 6 | Telegram tasks held only weakly by asyncio | messages silently vanish |
| 7 | Poller's frame block caught only network errors | our own bugs restart-looped the node |

Two deserve the detail.

**Defect 1 was caused by the 2026-09-08 fix in these same notes.** Moving recognition to
`run_in_executor` unblocked the event loop, and in doing so removed the accidental
serialisation that had been keeping one shared `FaceDetectorYN` safe. Six pollers can now be
inside `detect()` simultaneously, and `detect()` is two steps - `setInputSize()` then
`detect()` - so two threads with differently-sized frames can interleave and have one detect
at the other's dimensions. Fixed with one lock around the cv2 objects and the roster. This
costs nothing that was wanted: the goal was a free event loop, not parallel inference, and the
measured 1.9 ms worst-case loop gap is unaffected. A fix creating the next defect is worth
noting honestly rather than presenting the sequence as steady progress.

**Defect 2 is the one that would have been blamed on the wrong thing.** Everything is stored
in UTC, correctly. But `hours_from`/`hours_to` are typed into the Staff page by a person who
means local time, and they were being compared against a UTC clock. In BST that is an hour:
at 22:15 local the system believed it was 21:15. The Cleaner beat (18:00-20:00) would have
admitted at 20:30 local while the beat calls for a refusal - and on camera that reads as "the
policy engine is broken", not as a timezone bug. The 19 policy tests never caught it because
they pass explicit `datetime` objects; the defect was in the caller, not in `policy.py`.
Storage stays UTC; only the comparison moved, to `policy.policy_now()`.

Six regression tests added (`tests/test_review_regressions.py`), each failing against the code
as it stood that morning. Suite: 74 tests, all passing, server verified to boot and serve.

### Recognition and rotation were blocking the shared event loop, 2026-09-08

**Status: fixed, verified two ways.** Marin reported the dashboard's camera tiles looked
"badly choppy - maybe one frame every few seconds" and asked how many. The honest answer:
the boards were offline at the time (still being wired for the Uno work), so the exact figure
he saw could not be reproduced live. What could be checked without hardware was whether the
brain's own code was capable of causing exactly that symptom, and it was - a real deviation
from `docs/BUILD_PLAN.md`'s own stated design ("inference goes to run_in_executor, the event
loop is not blocked") that had not actually been implemented.

`app/recognition/engine.py`'s `detect()` and `embed()` are OpenCV DNN forward passes - CPU-
bound - and `app/nodes/frames.py`'s `rotate_jpeg()` does a decode/rotate/re-encode, also CPU-
bound. Both were being called directly on the asyncio event loop, which is the ONE thread
shared by all six nodes' polling loops and every HTTP response the server makes - including
the dashboard's own tile fetches. Measured on this hardware with the real models: rotate
~5.4 ms, detect ~11.6 ms, embed ~5.5 ms - about 22.5 ms of pure blocking per face, per frame,
per camera-on node. For as long as that runs, nothing else on the server can proceed: not
another node's poll, not a `/frame.jpg` response to a waiting browser tab.

Fixed by moving all three (`rotate_jpeg`, `detect`, `embed`, and the JPEG decode in
`events_sink.py`'s `frame()`) onto `loop.run_in_executor`, so they run on a thread pool
instead of the event loop itself.

Verified two ways, without needing the boards back up:

1. **A direct before/after measurement of loop responsiveness.** A background coroutine ticks
   as fast as `asyncio.sleep(0)` allows and records the gap between ticks - a blocked loop
   shows up as one large gap. Calling `detect()` directly (the pre-fix code path): the ticker
   froze for **16.6 ms**, matching the 16.5 ms `detect()` itself took - the loop was blocked
   for the entire call. After the fix, running the real `BrainEvents.frame()` end to end
   (decode + detect + embed, ~24.8 ms of real work): the largest gap was **1.9 ms** - the work
   still happens, but the loop is free while it does.
2. The full test suite (68 tests) still passes.

**What this does not claim:** that this was the entire cause of what Marin saw. 22.5 ms per
node, even across six nodes worst-case, sums to roughly 135 ms - real, and now removed, but
not obviously enough on its own to produce multi-second gaps on a single tile. A second,
independently measured cause already on record (2026-09-03) is WiFi airtime contention when
several nodes are clustered with cameras simultaneously awake, which produced spikes up to
2.1 s in that earlier test. Both are real; which dominates what Marin actually saw needs a
live measurement once the boards are back up; noted as the next thing to check, not asserted.

### Loopback exempt from the admin token, 2026-09-07

**Status: built, confirmed with Marin before implementing.** After the mobile fixes above, he
clarified his actual priority: not the phone, but the Mac itself - enrolling for the
presentation has to be one click, no dialog.

Weakening an auth check is exactly the kind of change worth pausing on rather than pushing
through, and it was: the edit was first blocked by an automated safety classifier for
modifying an authentication check, which is the right instinct for that class of change. The
reasoning was laid out to Marin explicitly and he confirmed before it was made.

The reasoning: whoever can already reach `127.0.0.1` on this machine can open `server/.env`,
kill the process, or edit the database directly. Gating enrolment behind a token on that
specific path adds ceremony without adding protection - the token's actual job is to stop
*another device on the network* from doing something destructive, and a request from the
machine itself was never the threat it defends against.

The exemption is narrow on purpose and checked empirically before relying on it: even a
request this Mac sends to its own LAN address arrives at the server with the LAN IP as the
source, never `127.0.0.1` - confirmed by watching the access log for both. So the exemption is
specific to the literal loopback address, not a looser "anything from this machine" test that
could be spoofed or misjudged. `POST /people/enroll` and `POST /reset` from `127.0.0.1`
without a token now return the normal business-logic response (verified: 404 for an unknown
node, `{"ok":true}` for reset) rather than 401; the identical requests from the LAN address are
still refused with 401. The client-side prompt is also skipped when the page itself was opened
via `127.0.0.1`, so nothing pops up asking for a token that the server does not require.

Full test suite still green (68 tests). This does not weaken what the token defends against -
a phone or any other device on the shared hotspot - only removes a check that was never
protecting anything on the one path where it fires.

### Marin could not enrol from his phone, 2026-09-07

**Status: fixed, verified in a real browser at a real mobile viewport.** Reported directly:
"I tried to enrol today and couldn't - it asked for the admin token."

Reproduced rather than assumed. Opening Staff on a phone viewport showed the real cause was
two compounding problems, not the one reported:

1. **The page itself was unusable on a phone.** Staff and Dashboard were built as fixed
   desktop grids (a 330px sidebar plus a detail pane; a 62/38 two-column split; 6-column
   zone/tile grids) with `body{overflow:hidden}`, correct for the 1080p recording the
   dashboard is explicitly designed for, wrong for a phone. On an actual mobile width the
   enrol form - the Capture button included - was rendered off-screen to the right, reachable
   only by scrolling a page that was never meant to scroll horizontally. Settings had the
   same fault in its node-calibration section, which `docs/FIELD_DAY.md` explicitly sends an
   operator to use standing at a board in the yard.

   Fixed with a `@media (max-width: ...)` block per page: stack what was side-by-side, let
   the page scroll vertically instead of each pane scrolling in its own fixed-height box, and
   verified in a real mobile viewport that no page requires horizontal scroll and the enrol
   form, in particular, is fully reachable and legible.

2. **The token prompt itself worked correctly** - reproduced by clearing the browser's stored
   token and clicking enrol: the native prompt fires exactly as designed, asking for
   "Admin token (from server/.env)". The design was sound and the instruction was not: a
   phone standing at a camera in the yard has no path to that file. Fixed by printing the
   token in `run.sh`'s startup banner, the same place already read for the LAN URLs, with a
   note that it is entered once per device and then remembered.

A third, smaller fault surfaced while reproducing this: a wrong or missing token returned
FastAPI's default `{"detail": "..."}` body, and the client only ever read `.error`, so every
auth failure showed a hardcoded "Enrolment failed." instead of the actual reason. Fixed to
read `j.error || j.detail`, so a future auth problem says what it is.

This is the same lesson as the settings-effect finding a few hours earlier, from the opposite
direction: the mechanism (auth, in both cases) was correct, and what had not been verified was
the actual path an operator takes to use it - here, specifically, from the device the design
assumed rather than the device it will actually be used from.

### Pre-shoot adversarial review: two real defects, 2026-09-07

An adversarial review was run over the whole system five days before filming, specifically
asking what would waste a field day rather than what was untidy. Five independent reviewers by
dimension, each finding then attacked by a separate skeptic whose default was to refute.

The run was cut short by a session limit: of roughly sixty candidate findings, only two
completed verification. The remainder are **unverified and are not treated as defects** -
unverified review output has a high false-positive rate and acting on it would be worse than
ignoring it. Both verified findings were then independently confirmed by hand before being
fixed.

**1. Seven of ten settings were written, audited, persisted, and read by nothing.**
`confirm_frames`, `dwell_ms`, `gate_bind_window_s`, both alert throttles, `voice_enabled` and
`telegram_enabled` were all exposed on the Settings page and stored in `config_kv`, while the
running code used module constants and default arguments. The page said "saved", the value
survived a restart, `audit_log` recorded a `config_change` - and nothing changed.

Two things made this worse than a dead control. The audit row asserted a change that did not
happen, in a table whose whole purpose is to be trustworthy evidence. And it removed the
tuning lever precisely during the week it was most needed: adjusting dwell or the gate binding
window from the yard is exactly what field calibration consists of.

Fixed by wiring the readers rather than deleting the controls, since the tuning is wanted.
Values now flow through a small cache (`db/repositories/config.py`) with a 2 s TTL and explicit
invalidation on write - which also removed an existing inefficiency, since the recognition
thresholds had been fetched with a fresh query on every frame, about eighteen queries a second
for values that change weekly.

The deeper lesson, and the one for the report: **the original verification tested persistence
and never tested effect.** The settings page was recorded as "built and verified" on the
strength of a value surviving a restart. `tests/test_config_effect.py` now asserts behaviour
change rather than storage.

**2. `cards.h` was being mirrored to the corporate OneDrive drive.**
The RFID card UIDs are excluded from git, with a comment saying why - a UID is a credential,
and anyone who knows one can write it to a blank card. The backup script's exclude list did
not cover it, and the script's own post-run leak check did not look for it either, so it
copied the file and then reported success.

Nothing had leaked yet: the mirrored copy was still the template. But beat 7 requires a real
UID in that file before filming, and the next commit after that would have shipped a working
gate credential to a school-managed drive while asserting all was well.

This is the *second* instance of the same class of fault in this project, in the opposite
direction: days earlier, a blanket `**/staff/` rule meant for biometric data silently swallowed
a source file. Both are the same underlying error - a protection rule and the thing it protects
drifting apart, with an automated check that did not actually cover the case. Fixed by
excluding the file, extending the leak check to assert it, and re-running with
`--delete-excluded` to purge the copy already sitting in OneDrive.

### Rotating credentials for the failover: considered and declined, 2026-09-07

**Status: designed, not built - and the reasoning is the point.** Recorded in full because a
rejected design with a stated reason is stronger evidence of engineering judgement than a
list of what was built.

Marin proposed replacing the RFID card with one-time codes delivered over Telegram: while the
system is healthy the brain issues each person a code and pre-loads it into the Uno; when the
system fails the codes are sent to their phones; a code is entered at the gate and dies on
use; on recovery the codes rotate.

The rotation half is genuinely better than what is built. A card UID is static and clonable by
anyone who learns it; a one-time code is neither. That is a real improvement and it is why
this is recorded rather than dismissed.

The delivery half cannot work, for a reason that generalises: **it depends on the thing that
failed.**

* Telegram is sent by the brain, over the internet. Of the three failures that trigger
  failover - the gate ESP32 dies, the ESP32 loses WiFi, or the brain itself dies - the third
  leaves nobody to send. That is precisely the case the third layer exists for, so the
  fallback would be absent exactly when it is most needed.
* The recipient's phone needs working network to receive the message. If the network is what
  broke, and it is one of the likelier faults, the code never arrives.
* Loading fresh codes *into* the Uno needs a channel to the Uno. It does not have one, by
  design - that is why its card list is compiled in. Any rotating secret needs a channel, and
  a channel is a dependency, which is the property this layer exists to not have.

A synthesis does survive the first two objections: deliver the code **in advance**, while
everything is healthy, rotating it periodically, so it is already on the phone before the
failure. It still needs a keypad the project does not have, and it still needs a channel to
the Uno for the matching secret.

The more elegant variant, and the one worth naming as future work: rotate the secret **on the
card itself**, rewritten by the reader during a normal healthy passage. MIFARE Classic sectors
are writable, so the credential could change on every use with no channel to the Uno at all -
keeping the no-network property *and* getting rotation. It needs a reader on the gate ESP32 as
well as the Uno, and key management on a microcontroller with 2 KB of RAM.

**Decision: keep RFID.** The properties that matter for a last line of defence are that it
needs no network, no internet, no charged phone and no delivery. The card has all four; every
alternative examined trades one of them away for rotation. Rotation is the right thing to want
and the wrong thing to buy at that price.

### The Uno's card list is a mirror, and mirrors go stale

`cards.h` is the Uno's own copy of UID-to-name, compiled into the firmware because the board
has no network and nobody to ask. That has a consequence worth stating plainly rather than
discovering later: **suspending someone on the server does not reach the Uno.** During an
outage, a revoked person's card still opens the gate.

This is the classic offline-door-reader problem and it has no clean answer without a channel,
which is the same trade examined above. It is bounded in practice - it only applies while the
smart path is down, and the journal records who came in - but it is a real gap and belongs in
the limitations column, not glossed over.

### Overstay detection and audit export, 2026-09-03

**Status: built and verified.** Overstay is the one anomaly nobody triggers: no camera sees an
event, no sensor fires, nothing happens. It is the *absence* of an event, which is why it has
to be a timed sweep rather than a reaction.

The deadline comes from `policy.overstay_deadline`, which is pure and already tested against
the case that broke the previous build - a shift ending after midnight, handled by anchoring
to the entry timestamp rather than to "today". Verified live: a person who entered at 09:00 on
a 09:00-17:00 shift, with a 5-minute grace, was flagged at 18:02 as **57 minutes past their
expected departure**. The arithmetic is right and the message says the number rather than just
"overstaying".

One alert per stay, and the flag that enforces it is a **database column, not a variable**.
The previous build tracked it in a process-local dict, so every restart re-alerted the
dispatcher about everyone still on site - the same class of fault as an in-memory strictness
flag silently reverting. Verified that a second sweep 35 s later did not re-alert, and that
leaving clears the flag (along with the session token) so a person's next visit is a fresh
stay that can alert again. A take reset clears it too, since a new take is a new stay.

`GET /audit.csv` exports the whole trail with person and zone names resolved from their
foreign keys, filename stamped with the export time. This is the report evidence: the audit
table reproduces the old flat log with `SELECT ts, message ORDER BY ts`, but severity and the
joins make it queryable in a way the old text file never was.

### Admin authentication (threat model A7), 2026-09-03

**Status: built.** A7 sat at "partly implemented" for the entire life of the previous build:
it had an audit trail and no authentication at all, so every destructive action - delete a
person, revoke a token, wipe the database - was an unauthenticated GET that anything on the
network could fire, including by being linked to.

A shared secret in a header (`X-Charon-Admin`), guarding mutating routes only. The shape is
the argument:

* Reads stay open on the LAN. The gate terminal is a phone propped outdoors that nobody is
  going to sign into mid-take; a login prompt there would be a fail-secure mechanism that
  fails the shoot instead.
* One secret, not accounts. There is one operator; per-user identity would be ceremony.
* Header, not query string, so it stays out of server logs and browser history.
* Compared with `hmac.compare_digest`, and an empty configured token logs a startup **warning**
  rather than passing quietly - a system that is silently unprotected is worse than one that
  is openly unprotected.

Verified: every mutating route returns 401 with no token and with a wrong token, 200 with the
right one; `/nodes`, `/people`, `/audit`, `/frame.jpg` and the dashboard all stay open.

Honest scope, and the report should say it this way: this is a shared secret over plain HTTP
on a private network. It stops an accident and a casual passer-by on the same LAN. It does not
stop anyone who can see the traffic. TLS and per-user credentials remain designed-not-built.

### Voice and phone notifications, 2026-09-03

**Status: built.** 13 lines pre-rendered by `tools/make_voice.py` with macOS `say -v Daniel`
(en_GB): a personal welcome per cast member, a denial per zone, and generic fallbacks so
someone who joined the cast late is still spoken to rather than met with silence - a silent
system on camera reads as a broken one. Verified as real audio (1.4 s and 2.1 s, 22 kHz
mono) and played back.

Nothing is synthesised at runtime. DEMO_ARCHITECTURE §7 asks for pre-generated calm lines with
no live LLM and no runtime API; the practical argument is stronger than the aesthetic one,
which is that the shoot then cannot be broken by a network hiccup or an expired key.

Playback runs on one dedicated OS thread draining a queue. `afplay` blocks, so calling it from
async code would stall every node's polling for the length of the line, and two lines started
at once would talk over each other - which sounds broken on camera in a way a slightly late
line does not. A line that has waited more than 6 s is dropped rather than played: "welcome"
ten seconds after someone walked through is worse than nothing.

Telegram reuses the existing `@CharonGBS_bot`, confirmed still live via `getMe`. The token was
moved into `server/.env` (gitignored, and excluded from the OneDrive mirror). Sends are
fire-and-forget: if Telegram is slow or down, the light still goes green, the voice still
plays, the audit row is still written, and only the phone notification is missing.

### Staff page and just-in-time grants, 2026-09-03

**Status: built and verified end to end through the real UI.**

The JIT panel only offers what a person *lacks* - a zone held permanently by their role shows
"held permanently" with no controls at all. This was the strongest single idea in the previous
build's console and is carried forward deliberately.

The headline beat was verified as a policy outcome, not just a UI state. An IT-role person
(role zones: Reception and Server room) was granted Workshop for 15 minutes through the page,
and the policy layer then answered:

| Zone | Now | In 20 minutes |
|---|---|---|
| Reception | ALLOW (role) | - |
| Warehouse | DENY | - |
| Workshop | **ALLOW (grant)** | **DENY - lapsed on its own** |
| Server room | ALLOW (role) | - |

That is the privilege-creep argument made concrete (threat model A4): there is no revert step
for an admin to forget, because there is no revert step.

Zone overrides in the editor say plainly that ticking anything replaces the role's zones *in
both directions* - it is how you give someone less than their role, not only more. That
direction is the authorisation gap the old build had, where an ADMIN could not be restricted at
all. Ticks identical to the role's own zones are stored as "inherit" rather than as an
override, so the distinction stays meaningful.

Deletion was verified to cascade: a deleted person takes their embeddings, grants and zone
overrides with them, which is the GDPR-relevant behaviour rather than an accident of schema.

### Settings page, 2026-09-03

**Status: built.** Every control carries a plain-language name *and* a sentence saying what it
does and what changing it costs - the old console's cryptic toggles were a named complaint
that had already been fixed once, and this is the thing not to regress on. Tuning values live
in `config_kv`, so they survive a restart (REBUILD_PROMPT §0.6.6: an in-memory strictness flag
that silently reverts is its own failure mode), and every change is audited with the full
before/after set.

Sensor thresholds are proxied through to the board's own NVS rather than stored centrally,
because the node's copy has to keep working when the brain is not running - and because six
boards on six walls must never need a USB cable to be recalibrated.

Verified: a change saved through the page, appeared in `audit_log` with actor `admin`, and
survived a full restart.

### Dashboard, 2026-09-03

**Status: built and verified in a real browser at 1920x1080**, the resolution the shoot
records at. `server/static/dashboard/index.html` - hand-written HTML/CSS/JS with no build
step, deliberately: one fewer moving part to break the day before filming.

Design choices, all of them reactions to specific faults found when auditing the previous
build's console rather than taste:

* Nothing smaller than 13px anywhere, and state is never carried by colour alone. The old
  console put its most important text (operator action results, alert lines) at 10-12px grey
  in a corner, which disappears entirely once a recording is scaled.
* **Three node states that cannot be confused**: `live` (green), `armed · camera off`
  (blue-grey), `offline` (red, plus a header banner naming the nodes). DEMO_ARCHITECTURE §6
  is explicit that a sleeping camera must never look like a dead one - during this session a
  real node genuinely dropped and the distinction read correctly at a glance.
* **Six columns, not four**: the four zones plus `On site · zone unknown` (someone who has
  entered but not yet been placed by a zone camera, which is the direct consequence of not
  auto-placing entrants in Reception) plus `Off site`.
* **Card movement animates via FLIP**, verified mechanically rather than by eye: moving a
  person between columns applies an inverting transform of `translate(387.8px, 0)` - exactly
  the measured gap between those two columns - before transitioning it away. The old board
  replaced its innerHTML wholesale, so a person vanished from one column and appeared in
  another between frames, and the zone-to-zone movement that is the video's central visual
  was invisible as movement.
* **Anomalies are large full-width cards** with an uppercase kind, the name and reason, and a
  timestamp; tailgating is amber, everything else red. The old build's alerts were 12px
  monospace lines identical in weight to routine traffic.
* **Camera tiles are pinned to their node for life** (REBUILD_PROMPT §0.6.4) and served from
  the brain's frame cache, so six open dashboards do not cost a node six times the requests.
* **No native `alert()`/`confirm()` anywhere** - the old console used OS dialogs for
  destructive actions, which show the page URL and sit outside the app's visual language on a
  recording. `Reset take` is a two-click arm that disarms itself after 4 s, verified working.

`POST /reset` deliberately does **not** wipe `audit_log`, unlike the old build's `/reset`
which deleted the whole trail. A take reset clears live state only (presence, zones, tokens,
and the in-memory gate/zone trackers, which would otherwise let a stale pending decision from
the previous take bind to the first passage of the next one) and writes one audited line, so
re-shoot boundaries are visible in a permanent record rather than erasing it. Verified: 5
test people all flipped off-site with zones and tokens cleared, one `reset_take` row written
by actor `operator`, and all 221 existing audit rows intact.

One bug found and fixed during browser verification: `/people` was not returning the zone
*name*, only the raw `at_zone_id`, so every on-site person landed in the "zone unknown"
column regardless of where they actually were. Caught immediately by looking at the rendered
board - the kind of thing no unit test would have flagged, because both halves were
individually correct.

### Gate and zone decision logic, verified live end to end, 2026-09-03

**Status: built.** `app/recognition/gate.py` and `app/recognition/zones.py` implement the
gate model Marin locked in over DEMO_ARCHITECTURE's original camera-only proposal: recognition
names someone and issues a decision (BEAT 1 - green/red, and where the decision is bound for
a passage to claim), but presence only flips when the PASS ultrasonic's counter actually
increments (BEAT 2). Both modules are pure functions - no database, no camera - and carry 24
unit tests between them, several of which are regressions of gaps the previous build had:

* **Denied but crossed anyway** never had an event at all in the old build; here it is its own
  alert (`denied_crossed`), distinct from a clean `entry`.
* **A passage with no fresh decision to bind to** ("unidentified passage") was only ever
  logged at ENTER in the old build and silently ignored at EXIT. Both directions now raise it.
* **Tailgating** (more than one face at the moment of passage) is flagged as its own alert
  alongside whatever the primary outcome was, not folded into it.
* Zone logic processes **every** face in frame, not just the largest - REBUILD_PROMPT §0.6.5's
  named blind spot. A second known person and a stranger sharing one frame both get their own
  correct outcome in the same pass.

Verified live against a real person, not only unit tests. Marin stood in front of gate-in;
enrolling and recognising him fired a real `gate_decision` event through the actual running
pipeline - visible on the live SSE stream and in `audit_log` a moment later, both carrying the
correct name, node and outcome. Before he was enrolled, three real pass-sensor trips (desk
handling) correctly produced three `unidentified_passage` alerts rather than silently doing
nothing or crashing - proof the passage-binding wiring executes correctly against real sensor
data, not just fabricated test input.

**Honest gap for today:** a genuine sensor-confirmed `entry` was not captured live - the pass
ultrasonic did not trip again in the ~12s window after the decision fired, most likely because
the physical pass sensor was not within reach of where Marin was sitting for the test. The
`entry` code path itself is not unverified, though: it is covered by a dedicated unit test
(`test_beat_one_then_beat_two_granted_entry`) exercising the exact same pure sequence, and its
database-writing half (`presence.commit_entry`) is structurally identical to `denied_crossed`
and `exit`, both of which the concurrent-entry and exit-without-entry logic paths share. A real
live passage capture is worth doing once field recon resumes and the boards are back at their
actual mounted positions.

### A board on USB power flaps on WiFi while battery-only boards do not, 2026-09-03

**Status: confirmed by a controlled before/after test on live hardware.**

While building the brain skeleton, the audit log showed one board (zone-workshop) cycling
offline/online every 8-90 seconds, while the other five - all on battery power only - logged
exactly one online event each since the brain started and never flapped again. The only
difference: zone-workshop had a USB cable connected (left over from reading its MAC a few
minutes earlier), while the other five did not.

Test: leave everything else running, unplug the USB cable from zone-workshop only, watch the
audit log for 150 s. Result: **zero offline events in 150 s**, against a prior pattern of one
roughly every 8-90 s. Nothing else about the board or the network changed in that window.

Plausible mechanism, not yet isolated further (not worth the time on a two-week schedule):
USB and WiFi share the same SoC, and either power-rail noise from the USB connection or CPU/
interrupt contention between the native USB CDC stack and the WiFi stack is degrading the
radio while both are active. Whichever it is, the practical rule is simple and now backed by a
measurement rather than a hunch: **a board is for flashing on USB, then it goes fully to
battery before any real test.** This matters operationally - it means a "let me just plug in
and check something" during a dry run can quietly reintroduce instability that has nothing to
do with whatever was actually being checked.

### microSD on the zone boards

**Status: designed, not built.** 2026-09-03. The four interior boards carry a microSD slot
with cards already inserted, unused. This maps directly onto threat model B3 ("single point
of failure - one brain"), which already records store-and-forward to microSD as a documented
design, not implemented. Ranked by cost against value if ever built: (1) a local, brain-
independent audit log of near-sensor trips and wake events - cheap, and a genuine
defense-in-depth story extending the gate's Uno failover to the interior zones; (2) full
store-and-forward buffering of brain-bound events during a network drop, replayed on
reconnect - the literal B3 mitigation, higher complexity (replay/sync logic); (3) crash-dump
forensics for build-time debugging - useful to us, not report-facing.

Deliberately not pursued now: the wiring of the SD slot on this specific (generic, unbranded)
board is unverified, and the four remaining free GPIOs on a zone board (21, 42, 47, 48) may
not be enough for 4-bit SDMMC - a real risk of conflicting with the already-soldered near/pass
sensor pins (38-41) on cheap clone boards. `DEMO_ARCHITECTURE` is explicit that untested
robustness which never appears on camera is a report improvement, not a build target; this is
exactly that.

## Still to write up

- The Arduino Uno's role as an evolution of the decision, not a pre-existing design. The
  "Heracles" concept that `REBUILD_PROMPT` §5 points at is **not documented anywhere** in
  either repository; the single sentence in that document is its entire recorded content.
  The report must present this honestly rather than implying a finished earlier design.
- The rebuild itself as the LO3 iteration story: the archived 18.07 plan versus the current
  one, and specifically why the Uno moved off USB serial and onto a standalone heartbeat wire.
- Threat model rewrite: several items marked *implemented* describe the old prototype, and
  A6 still describes the recogniser as LBPH when it has been YuNet + SFace since before this
  rebuild started.
