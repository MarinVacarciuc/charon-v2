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

**Status: built and validated on hardware.** 2026-09-02, soak-tested 2026-09-03.

Each node keeps its camera powered down and initialises it only when the ultrasonic near
sensor reports someone within range, sleeping again after 20 s idle. WiFi stays up
throughout, which is also a power requirement: a true deep sleep drops the current draw
below the 18650 boost-converter bank's auto-cutoff and the pack switches itself off. That
is a measured property of this specific power hardware, not a firmware bug.

This is the privacy-by-design and energy-efficiency argument for LO4: the system does not
record until there is something to record. `[CITE: data minimisation / privacy by design -
UK GDPR Art. 5(1)(c) and Art. 25]`

*Risk resolved 2026-09-03.* The 108-cycle bench soak passed with no failures, no reboot
and no heap leak (see Measurements). The fallback of keeping the camera initialised while
idle is not needed, and the energy and privacy claim is a measured feature rather than an
aspiration.

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

The ~1 s wake is the reason the near sensor wakes the camera rather than the first frame
request: at a walking pace, 2.5 m of approach is about the margin needed for the camera to
be ready by the time a face is in frame.

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
