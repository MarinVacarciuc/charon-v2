# Charon — working prototype

**Status (2026-07-04):** a working face-based access-control system running end to end on a laptop plus two phones. It began as week-1 feasibility spikes and has grown into the core of the Charon design: live recognition at the gate, a server-side model of who is on site, self-expiring temporary access, interior zone authorisation, overstay and anomaly alerting, and a single-screen admin console.

Everything here runs on a trusted LAN and is deliberately un-hardened (plain HTTP, no auth). That is a conscious prototype choice; the threat model and hardening are documented as separate design work (see "Security posture" below) and are themselves report material for a cyber-security unit.

---

## 1. What it does

1. A network camera feeds the laptop, which **detects and recognises** faces (a DNN pipeline: YuNet detector + SFace 128-d embeddings, cosine match).
2. At the gate the laptop decides **grant or deny** against a live policy (role, hours window, validity date, suspension), draws a labelled green/red box, and the gate terminal **speaks** the decision.
3. The **server, not the phone, holds the truth of presence.** A recognised entry marks the person on site and issues a live token to their phone over Telegram. A recognised exit marks them off site and **annuls the token**. The token is a receipt, not the enforcement.
4. Because presence lives on the server, two whole classes of attack are closed: a **stolen phone after exit** (its token is dead once the person is off site) and a **parallel session** (the same identity cannot be admitted twice; a second entry while already inside raises an alert).
5. An admin can grant **just-in-time temporary access** that expires on its own (extra hours, or specific zones each with its own expiry), so nobody has to remember to revert it.
6. Interior zones (the future Cerberus layer) are authorised the same way: presenting a badge at a zone the person may not enter is denied and the dispatcher is alerted.
7. A **dispatcher** (and only the dispatcher) receives security alerts: void-token use, unauthorised zone, concurrent entry, exit-without-entry, and overstay.
8. The whole operation is driven from one **2x2 admin console**: enrol, staff list and editor, a live gate monitor, and an on-site board showing who is in which zone.

---

## 2. Architecture

```
  camera phone            LAPTOP (the "brain", :8770 + static :8765)          credential phone
  (IP Webcam)      -->    detect + recognise + policy + presence       -->    Telegram token
   /shot.jpg              draws box, holds state, serves pages                (@CharonGBS_bot)
                                     |
                          +----------+-----------+
                     gate terminal            admin console
                     (pip.html, voice)        (admin.html, 2x2)
```

| Device | Role |
|---|---|
| MacBook | the brain: detection, recognition, policy, presence, alerting; serves the processed video, the JSON state, and the pages |
| Camera phone (IP Webcam app) | streams the gate camera over the LAN as `/shot.jpg` (currently the Kali S10, front camera, portrait) |
| Gate terminal | a phone in Chrome full-screen on `pip.html`: shows the box, speaks the decision, has the ENTER/EXIT switch |
| Credential phone | receives the token in Telegram; walked around the "premises" to test presence and exit |

All on the same LAN (home Wi-Fi for now; an own private router is the plan, which also answers the college-network client-isolation problem).

---

## 3. Core ideas (the design, not just the code)

- **The token is a receipt, enforcement is live and server-side.** Editing a person's record takes effect immediately against the same token, and revoking presence (exit) makes the token worthless. This mirrors short-lived STS credentials rather than a long-lived badge.
- **Presence is the source of truth.** `presence` (in/out), `entry_time` and a per-entry `session` nonce live on the server. The gate flips them; interior readers and the admin consult them.
- **Direction comes from the terminal, meaning comes from the server.** The gate runs in ENTER or EXIT mode (the two sides of a turnstile). The server decides what an appearance means from the mode plus current presence: entry, exit, concurrent-entry alert, or exit-without-entry anomaly.
- **Least privilege and just-in-time.** Temporary access only ever grants what a person lacks; permanent zones are shown as already covered, and someone with full permanent access has nothing to grant. Grants carry their own expiry and are simply ignored once past, so there is no "admin forgot to revert" privilege creep.
- **Alerts go to a dispatcher, not to everyone.** Only staff flagged as dispatcher (or, failing that, an ADMIN with a chat) receive security alerts.

---

## 4. Files (`prototype/`)

| File | What it is |
|---|---|
| `process_server.py` | the brain (:8770). Camera loop, detection + recognition, policy, presence, gate logic, temporary grants, zone authorisation, overstay watch, alerting, and the whole HTTP API |
| `pip.html` | the **gate terminal**: processed video + box on top, event log below, speaks entry/exit/alert (Web Speech), ENTER/EXIT mode switch, on-site count |
| `admin.html` | the **admin console**, one screen in a 2x2 grid: New staff / capture, Staff list + editor, Charon gate monitor, On-site board |
| `board.html` | the standalone **on-site board** (same view as the admin quadrant, for a second dispatcher screen) |
| `enroll.html` | legacy enrol station, now just redirects to the admin console (enrolment moved inside) |
| `start.command` / `stop.command` | double-click launchers for the Mac servers; camera IP is set once in `CHARON_CAM` at the top of `start.command` |
| `face_spike.py`, `stream_spike.py` | the original spikes (recognition on the Mac; recognition from the network camera) |

The two DNN models are **not committed** (they are data, and the SFace model is ~38 MB). Fetch them once into `prototype/`:

```
curl -L -o face_detection_yunet_2023mar.onnx  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
curl -L -o face_recognition_sface_2021dec.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
```

Biometric data (`staff/`, face crops, `meta.json`) and the Telegram token (`.tg_token`) are git-ignored (GDPR Art. 9, and secrets stay out of the repo). Python deps in a venv: `opencv-contrib-python` (for `cv2.face`), `numpy`.

---

## 5. How to run

1. **Camera phone:** IP Webcam -> Front camera + Portrait -> Start server -> note the IP.
2. Put that IP in `CHARON_CAM` at the top of `start.command`.
3. **Mac:** double-click `start.command`. It prints the stable `.local` URLs.
4. **Enrol:** open the admin console; the New staff quadrant shows the live camera. Set Name, Role, optional Telegram chat id, tap **Capture** a few times at different angles and lighting.
5. **Gate:** open `pip.html` on the terminal phone (tap once to enable sound). Set the mode (ENTER by default). Recognised + policy pass -> green box, name, "Access granted", token to the phone. Exit mode -> "Goodbye", token cleared.

Stable URLs (by hostname, so a DHCP IP change does not break them):

```
gate:   http://Marins-MacBook-Pro.local:8765/pip.html
admin:  http://Marins-MacBook-Pro.local:8765/admin.html
board:  http://Marins-MacBook-Pro.local:8765/board.html
```

---

## 6. Feature reference

### Recognition
A DNN pipeline: **YuNet** detects faces (with landmarks), the largest is aligned and passed to **SFace**, which produces a 128-d embedding. Enrolment stores the L2-normalised embeddings per person (as `emb.npy`, not raw crops, which is a better GDPR posture); recognition takes the cosine similarity against every enrolled embedding and accepts the best if it clears the threshold. This replaced the earlier Haar + LBPH, which was lighting/pose sensitive and prone to false accepts.

### Gate: mode, presence, token
- **Mode** ENTER or EXIT, set on the terminal (`/mode`), models the in and out readers of a turnstile.
- A recognised face fires a single event on the rising edge (a short per-person cooldown swallows flicker and lingering). A **denied** entry does not consume the edge, so a person who becomes authorised while standing there (shift start, or an admin grant) still gets in without stepping away.
- **ENTER** + off site + policy pass -> admit, set presence in, mint a `session` nonce, send `CH-<session>` to the phone.
- **ENTER** + already on site -> **concurrent-entry alert** (possible cloned identity or tailgating).
- **EXIT** + on site -> set off site, clear the session (**token annulled**), tell the person their token is void. Exit is always allowed regardless of policy (you can always leave).
- **EXIT** + off site -> **exit-without-entry anomaly**.

### Policy enforcement (at the gate, live)
`policy_ok`: denied if suspended; denied if past `valid_until`; otherwise granted only inside the hours window `hours_from`..`hours_to`, unless a temporary hours grant (`access_until`) is still active.

### Temporary access (just-in-time, self-expiring)
- **Hours**: extend the access window by any amount (`/grant kind=hours`).
- **Zones**: each zone is granted independently and keeps its **own expiry** (`zgrants` = a list of `{zone, until}`). One action can grant several zones with different durations; each can be cleared on its own.
- The admin UI only offers what the person lacks: permanent zones show as "permanent", 24/7 people show no hours extension, and someone with full access shows "nothing to grant".

### Interior zone authorisation (the Cerberus seed)
`zone_allowed` = effective permanent zones (the person's `zones` override the role default when set, otherwise the role) plus any active temporary zone grant. Two endpoints exercise it and stand in for real interior nodes until the ESP32s arrive:
- `/checktoken` (a controlled reader): off site -> token void + alert; on site but zone not allowed -> denied + alert; otherwise OK and the person's location is updated.
- `/atzone` (a presence sensor): records the person's zone and, if they are somewhere they may not be, records a zone violation and alerts the dispatcher.

### Overstay
A 30s background sweep flags anyone still on site past their allowed time (shift end, anchored to the entry date so it survives past midnight, or a `max_hours` on-site cap), after a 5-minute grace. It nudges the person and alerts the dispatcher once per stay, including the person's last known zone.

### Dispatcher alert routing
`dispatch_alert` sends only to staff flagged `dispatch=1` (or, if none, an ADMIN with a chat). If there is no recipient it writes an "ALERT UNDELIVERED" line to the audit log rather than dropping the alert silently. It never broadcasts to every worker.

### Admin console (2x2)
One screen: **New staff / capture** (always-live camera + fields), **Staff list + editor** (search, list, full per-person editor with permanent and temporary boxes, plus an audit-log overlay), **Charon gate monitor** (the processed feed, status, event log, and a mode switch, for the admin; silent), and **On-site board** (who is in which zone). People and presence refresh every 4s without clobbering a field being edited; the gate monitor refreshes every 0.4s.

### On-site board
Columns per zone plus an off-site column; each on-site person is a card with role, entry time, active zone grants, and an overstay flag in red.

---

## 7. HTTP API (`:8770`)

| Endpoint | Purpose |
|---|---|
| `GET /frame.jpg` | current processed frame (JPEG) |
| `GET /state` | JSON: `status, name, role, gate, gatename, gatemsg, event_id, mode, onsite` |
| `GET /people` | JSON list of person records + computed `samples, access_left, zgrants, zone_left, eff_zones, overstay` |
| `GET /present` | JSON list of names currently on site |
| `GET /enroll?name=&role=&chat=` | add a face sample (creates the person if new) |
| `GET /update?...` | set any editable field (role, chat, hours, valid_until, status, zones, max_hours, dispatch, newname) |
| `GET /grant?name=&kind=hours\|zone&mins=&zone=` | temporary grant (hours, or a zone with its own expiry) |
| `GET /ungrant?name=&zone=` | clear one zone (with `zone=`) or all temporary (without) |
| `GET /mode?m=enter\|exit` | set the gate terminal mode |
| `GET /forceout?name=` | admin: mark off site and annul the session |
| `GET /checktoken?name=&zone=` | interior reader check (presence + zone) |
| `GET /atzone?name=&zone=` | interior sensor: record a person's zone (+ violation alert) |
| `GET /delete?name=` / `GET /reset` | remove one person / clear the database |
| `GET /audit` | last lines of the audit log |

Query parsing keeps blank values, so clearing a field (for example emptying `zones` or `valid_until`) actually applies rather than being ignored.

## 8. Person record

`role, chat, hours_from, hours_to, max_hours, valid_until, status, zones` (permanent editable), `dispatch` (receives alerts), `access_until` (temporary hours), `zgrants` (list of per-zone `{zone, until}`), and the system-managed `presence, entry_time, session, at_zone`. The old single `grant_zone`/`grant_until` pair is migrated into `zgrants` on load and then left blank.

---

## 9. Security posture and honest limitations

- **No transport security or auth** on the prototype: plain HTTP on a trusted LAN. Production needs TLS, authenticated endpoints, and per-node credentials.
- **No liveness check yet**, so a photo could spoof the gate. The recogniser was upgraded from LBPH to a DNN embedder (YuNet + SFace), which largely fixes the accuracy and false-accept problems; liveness (blink / depth / challenge-response) is the remaining gap and is documented as the next step.
- **Presence is persisted**, so a crash while someone is on site leaves them marked in; the admin "Force exit" clears it. A production system would reconcile presence on restart.
- **Single brain** is a single point of failure; the design calls for a failover broker and encrypted store-and-forward on the nodes.

These are not oversights to hide; for a cyber-security unit they are the LO4 content (threats, mitigations, and the trade-offs behind each prototype choice).

---

## 10. Findings and fixes (LO3 iteration / LO4 evaluation)

From the build:
- **Termux from Google Play is dead** (bintray repos) -> install from GitHub/F-Droid.
- **OpenCV cannot open the phone camera in Termux** or the IP Webcam MJPEG stream -> poll `/shot.jpg`.
- **curl broke on Termux** (library mismatch) -> use wget or Python.
- **MJPEG in `<img>` flickers** -> JS double-buffering.
- **Camera upside down** -> rotate 180 on the Mac.
- **False accept** (a family member matched as the user) -> tighter LBPH threshold + require the decision to be stable ~1s.
- **Lighting sensitivity** -> CLAHE normalisation + enrolling under several lightings.
- **DHCP IP change broke the pages** -> pages address the Mac by `.local` hostname, not IP.

### Adversarial review pass
After the presence, per-zone-grant and board work, a multi-agent review (four independent lenses, each finding then verified by a separate skeptic) surfaced eight real issues, all fixed:
- **Per-person zones were additive only**, so unchecking a zone could not restrict below the role. Now the `zones` field overrides the role, and the UI seeds its checkboxes from the effective set.
- **Alerts were dropped silently** when no dispatcher was configured. Now they fall back to ADMIN, and otherwise log "ALERT UNDELIVERED".
- **A race** in the overstay sweep read the shared dict outside the lock; recipients are now snapshotted under the lock.
- **A denied entry latched the gate**, blocking a later legitimate entry; the edge is now only consumed when the event is actually handled.
- **Overstay stopped firing after midnight** because the deadline used the current date; it is now anchored to the entry date.
- Expired zone grants are pruned; migrated legacy fields are blanked; **quote-unsafe inline handlers** (a name with an apostrophe broke the buttons) now read the name from a data attribute.
- A self-found bug: `parse_qs` was dropping blank values, so cleared fields were ignored; fixed with `keep_blank_values`.

---

## 11. Planned next: Cerberus interior nodes

The interior layer is designed but not yet built (no hardware yet):
- **ESP32-CAM nodes**, one per zone, each a "head" guarding its door, feeding frames to the brain exactly as the gate camera does (`/frame.jpg?node=<zone>`), reusing the same detect and recognise pipeline. The `/checktoken` and `/atzone` endpoints already model their behaviour.
- **Sleep and wake-on-demand.** Nodes sleep when a zone is empty (a cheap ultrasonic or PIR sensor is the always-on trigger). On the admin gate grid a sleeping node is a black tile; tapping it wakes the camera (a server "wake" flag with an `awake_until` window, kept alive while the admin watches), and tapping again enlarges it. The key trade-off to settle with the hardware: remote wake needs the node network-reachable, so "sleep" means camera-off plus light sleep for mains-powered nodes, whereas true deep sleep (battery) can only be woken by motion. Camera-off is where most of the power goes anyway, and turning the camera on only when needed is itself an energy-efficiency and privacy-by-design point (LO4).
- A cheap way to prove the multi-camera admin UI before the boards arrive is a spare phone as a stand-in zone node.

---

## 12. Learning-outcome mapping (brief)

- **LO2** (emerging tech and its end user): the guard and dispatcher workflows are built and demonstrable; the on-site board and alerts are their situational-awareness tools.
- **LO3** (multiple iterations): the findings above are a real iteration trail (recognition -> network camera -> policy -> presence -> per-zone grants -> reviewed and hardened).
- **LO4** (ethical/social/economic/legal): biometrics and GDPR Art. 9, least-privilege and JIT access, dispatcher-only alerting, energy-efficient wake-on-demand, and the documented security limitations.
