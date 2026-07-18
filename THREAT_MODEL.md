# Charon — threat model

A short, honest threat model for the Charon access-control system. It maps the threats found during design and an adversarial code review onto the mitigations. Status is one of: **implemented** (in the prototype today, tested), **planned** (in scope, not yet built, usually needs the node hardware or crypto work), or **documented limitation** (accepted for the prototype and described in the report).

This is an academic, defensive project (BTEC HND Unit 21). All testing is against our own system on our own private network.

> Honesty note: an earlier version of this file marked several network/crypto items as "implemented". They were design intentions, not built. This version reflects what actually runs. The prototype's strength is the **access-control brain** (identity, presence, policy, alerting); the network, crypto and node hardware are mostly **planned**.

## Assets

- Staff biometric templates and enrolment data (special-category personal data, UK GDPR Art. 9)
- Live sessions / access tokens (`CH-<session>`), and the presence state (who is on site, in which zone)
- Movement, access and alert logs
- The controllers (laptop brain, gate phone) and the gate/zone nodes, plus their network link

## A. Identity and access control (the built core)

| # | Threat | Mitigation | Status |
|---|--------|------------|--------|
| A1 | **Lost/stolen phone, or a leaver keeps access** | The token is a receipt, not the enforcement: the server holds presence and decides live. A recognised **exit annuls the session**, and any token presented while **off site is denied + dispatcher-alerted** (`/checktoken`). Suspending or expiring a record takes effect immediately at the gate. | **implemented** (device-bound key + deny-list for the QR/BLE path: planned) |
| A2 | **Cloned identity / concurrent session** | One live session per person; a second **entry while already on site raises a concurrent-entry alert** (cloning / tailgating), and an **exit with no prior entry** is flagged as an anomaly. | **implemented** (camera-count vs token tailgating: planned) |
| A3 | **Unauthorised zone entry** | `zone_allowed` = role zones (with a per-person override that can also *restrict*) plus active temporary grants; `/checktoken` denies + alerts, `/atzone` records a violation + alerts. | **implemented** (logic; real interior ESP nodes: planned) |
| A4 | **Privilege creep (admin forgets to revert)** | Just-in-time, **self-expiring** grants (each carries its own expiry, ignored once past); the UI only ever grants what a person lacks (least privilege); every grant/edit is audited. | **implemented** |
| A5 | **Overstay / person not leaving** | Background sweep flags anyone on site past shift end (anchored to the entry date) or a max on-site cap, nudges the person and alerts the dispatcher with their last known zone. | **implemented** (out-of-band SMS / dead-man escalation: planned) |
| A6 | **Face spoofing (photo or video at the gate)** | LBPH with temporal persistence and CLAHE reduces false accepts, but there is **no liveness yet**; a photo could pass. Blink / depth / challenge-response and a DNN embedder are the upgrade. | **documented limitation** (liveness + stronger recogniser: planned) |
| A7 | **Weak enrolment / trust bootstrap** | Enrolment and every edit go through the admin console and are audited; unknown faces are refused. Endpoint **authentication** for the admin API is not yet in place. | **partly implemented** (audit); admin auth: planned |

## B. Availability and resilience

| # | Threat | Mitigation | Status |
|---|--------|------------|--------|
| B1 | **Node tampering / jamming / network loss (a node goes dark)** | Per-node **heartbeat**: no frames for > 6 s marks the node OFFLINE and raises a dispatcher alert, treated as a possible tamper/jam **security event**, not a glitch. | **implemented** (gate node; per-node as hardware lands) |
| B2 | **Outage stops the gate deciding** | The gate **fails safe on exit** (shows EXIT FREE, never traps people; passage logged) and **fails secure on entry** (OFFLINE, manual via the guard) when a node is offline or the brain is unreachable. | **implemented** (terminal state + policy); electric-strike fail-safe wiring and a door-local cached allow-list: planned |
| B3 | **Single point of failure (one brain)** | A standby brain on the gate phone takes over the gate only, with automatic failback and state merge; the phone can host a fallback hotspot so the gate becomes a self-contained island. Its network association is the arbiter, avoiding split-brain. | **documented design**; interior store-and-forward to microSD: planned |
| B4 | **Alert misrouting / silent drop** | Alerts go **only to a dispatcher** (flagged staff, else an ADMIN); if there is no recipient the event is written to the audit log as **ALERT UNDELIVERED** rather than lost. Never broadcast to every worker. | **implemented** |
| B5 | **Lone-worker alert fails silently** | Out-of-band alert (cellular SMS) and a dead-man's-switch on loss of the controller. | **planned** |

## C. Confidentiality and integrity of the plumbing (mostly not yet built)

| # | Threat | Mitigation | Status |
|---|--------|------------|--------|
| C1 | **Eavesdropping on the wire / air** | The prototype is **plain HTTP on a trusted private LAN**. Production: TLS with per-node credentials, shown by a wired red-team (cleartext then TLS). | **documented limitation**; TLS: planned |
| C2 | **Rogue node impersonates a gate/zone node** | Node attestation / pairing before a node is trusted; a lightweight IDS (new-MAC / anomaly) on the network. | **planned** |
| C3 | **Biometric data / logs read at rest** | Encrypted templates and node records (AES-256 on the S3), prefer non-reversible templates, a retention/deletion policy. Today `staff/` and the bot token are gitignored and never leave the machine. | **gitignore implemented**; at-rest encryption: planned |
| C4 | **Firmware supply chain** | Authenticated OTA on the private network (first flash by cable), signed images as production. | **planned** (OTA is the next firmware step) |
| C5 | **Untrusted college network** | Own private router and IoT segmentation, removing captive-portal / client-isolation exposure. | **planned** (own router to be set up) |
| C6 | **Token replay on the phone-credential path** | Short lifetime plus a server-side session tied to presence; a device-bound key answering a fresh server challenge (a true second factor). The gate path is face-gated, so a replayed token alone does not admit. | **partly implemented** (session/presence); device-binding: planned |

## Adversarial review

The presence, per-zone-grant and resilience code was put through a multi-agent adversarial review (independent finders, each finding verified by a separate skeptic). It surfaced eight real defects, all fixed, including an authorisation gap (a per-person zone restriction that did not actually restrict), a silent alert drop when no dispatcher was set, a race in the overstay sweep, and a gate edge-case that could block a legitimate entry. The details are in [`docs/PROTOTYPE.md`](docs/PROTOTYPE.md).

## Secrets and data handling

- No secrets in git: WiFi, the Telegram bot token and keys live only in `secrets.h` / `.env` / a gitignored token file; templates are provided.
- No biometric data in git: face images, embeddings and the staff database never enter the repository (`.gitignore` blocks `staff/`, face crops and metadata).
