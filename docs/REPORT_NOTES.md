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

**Status: built (firmware); pending hardware validation.** 2026-09-02.

Each node keeps its camera powered down and initialises it only when the ultrasonic near
sensor reports someone within range, sleeping again after 20 s idle. WiFi stays up
throughout, which is also a power requirement: a true deep sleep drops the current draw
below the 18650 boost-converter bank's auto-cutoff and the pack switches itself off. That
is a measured property of this specific power hardware, not a firmware bug.

This is the privacy-by-design and energy-efficiency argument for LO4: the system does not
record until there is something to record. `[CITE: data minimisation / privacy by design -
UK GDPR Art. 5(1)(c) and Art. 25]`

*Risk being carried:* repeated `esp_camera_init` / `esp_camera_deinit` cycling is not yet
proven stable over hundreds of cycles on this hardware. A bench soak test of 100 cycles,
logging free heap and die temperature, gates whether this ships. If it fails, the fallback
is a camera that stays initialised but serves no frames while idle, and the energy claim
becomes a measured limitation rather than a built feature.

---

## Measurements to date

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
| mDNS lookup, `AF_UNSPEC` vs `AF_INET` | 5.002 s vs 0.010 s | to re-measure in the brain |
| Own-face cosine similarity through the OV5640 | 0.63 to 0.93, typically 0.70 to 0.75 | to re-measure after re-enrolment |
| Continuous-streaming die temperature | 65 to 68 C | to re-measure with the wake/sleep cycle |
| Phantom passages without hysteresis | 6 in 8 s with nobody present | already fixed; cite as the reason hysteresis exists |
| Ultrasonic multipath on a cluttered desk | 13 to 200 cm frame to frame | reason thresholds are calibrated in place |

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
