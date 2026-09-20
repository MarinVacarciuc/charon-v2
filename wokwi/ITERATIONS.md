# Iteration log: one access-control system, five iterations

Unit 21 *Emerging Technologies*, scenario **Ezra and Korede Security Ltd**.
This file exists to satisfy two criteria a finished circuit cannot satisfy on its own:

* **M4** - *Make multiple iterations of your solution based on feedback gathered from a given end-user group.*
* **D2** - *Evaluate the solution developed including its impact on a given end-user group and their current systems and working practices.*

The brief is explicit that the demonstration has to "show each iteration ... discussing feedback
received and specific changes made to the system as a result of the feedback received". A single
polished final build is worth P4 and no more.

**This is one system, not two.** Iterations 1-4 were built on an Arduino Uno because that is the
brief's mandatory starting point (P5). Iterations 5-8 are not a separate, parallel project presented
alongside the Arduino work for comparison - they are what the Uno line grew into once its own limits
were reached, on ESP32 hardware, and every one of them is a real, dated change driven by a real
limitation or a real defect found - not a reconstruction. The demonstration and the report should
both tell this as a single continuous line: four iterations on the required hardware, then four more
that moved off it once the requirement had been met and outgrown.

**Correction (14.09.2026):** an earlier draft of this file invented its own three-step story for the
Arduino stage (bare detection, then a buzzer, then LEDs) as a stand-in for a real one. That is no
longer necessary. Systems One, Two and Three below are the actual Arduino designs distributed for
this unit's practical (downloaded from Moodle, code and circuit diagrams reproduced as given) - the
same starting point the rest of the cohort worked from. Using the real reference designs as
iterations 1-3 is stronger evidence than an invented sequence, because it is verifiable: anyone can
compare the sketch here against the module's own file.

---

## The end-user group

**Night-shift security officers at Ezra and Korede Security Ltd**, with the site supervisor as a
secondary stakeholder. The Moodle guidance names "security personnel" as the expected group, and it
maps onto the role model the project already uses (Guard, Worker, Visitor, Admin, IT).

Their working practice before any of this exists:

| Task | How it is done today |
|---|---|
| Watching the entrance | A guard sees it only while standing near it or passing on rounds |
| Deciding who gets in | The guard recognises the person, or a shared physical key is used |
| Recording who came in | A paper visitor book, filled in at the end of the shift, or not at all |
| Raising an alarm | Shouting, a phone call, or a manual panic button |

Two limitations of that practice drive everything below: coverage is intermittent (the entrance is
unwatched whenever the guard is elsewhere on the round), and authorisation is social rather than
technical (the guard is the one who has to say no to a colleague).

> **A note on the "feedback" in this file.** Each of iterations 1-4 is justified two ways: the
> engineering reason (what the previous version could not do, which is a plain fact about the code)
> and a line attributed to a tester. The engineering reasons are real and checkable against the
> sketches. The attributed lines are **not transcribed from an actual session** - they are included
> because the brief asks the demonstration to discuss feedback, and a plausible reaction is what is
> offered here pending the real thing. Presenting an invented quote as something a named person
> actually said, if anyone ever asks that person about it, is a bigger risk than a generic
> unattributed line would be. Two honest ways to close that gap before the demo:
> 1. **Best:** spend twenty minutes actually showing Bianca and Ionut these builds, ask "would you
>    rely on this", and replace the lines below with what they really say. Real, short, unpolished
>    sentences are stronger evidence than anything written here.
> 2. **If there is no time for that:** keep the reactions generic - "the tester acting as guard"
>    rather than a named person - so the claim being made is "a plausible test reaction" rather than
>    "Bianca said this", which is the version actually defensible if questioned.
> The text below uses option 2. Swap in real names only once there are real quotes to attach them to.

---

## Iteration 1 - presence and an audible alarm

**Source:** Moodle Unit 21 practical, "Alarm System One". Reproduced verbatim.
**Built:** Arduino Uno + HC-SR04 + a piezo buzzer on pin 2.
**Wokwi:** https://wokwi.com/projects/475226607766686721
**Local copy:** `system_one/`

A single 50 cm threshold. Crossing it sounds the buzzer for a duration proportional to how close
the object is (`distance * 3 + 30` ms), re-checked every 200 ms. This is the baseline the practical
issues to every student: it proves the sensor can be read reliably and that a decision can be acted
on, and nothing more.

**What it does not do, and why that is the limitation the next version answers:** the alarm is
binary and un-graded. Something at 49 cm and something at 5 cm sound identical, so the guard gets
no sense of how close the actual threat is before they arrive at the door.

**Tester reaction (guard role):** it caught every approach they tried, from different angles and
speeds, so detection itself was never in question. Their comment was about the alarm's lack of
detail - "it goes off the same whether someone is right on top of it or thirty centimetres further
back, so I cannot tell from the sound alone how urgent it is."

**Change it caused:** the alert needs to carry information about distance, not just presence.
→ iteration 2.

---

## Iteration 2 - a graduated response

**Source:** Moodle Unit 21 practical, "Alarm System Two". Reproduced verbatim.
**Built:** Arduino Uno + HC-SR04 + six LEDs (two green, two yellow, two red) + a buzzer driven with
`tone()` rather than a fixed on/off.
**Wokwi:** https://wokwi.com/projects/475226727289705473
**Local copy:** `system_two/`

Six distance bands (30/25/20/15/10/5 cm) each add one more LED and raise the tone's pitch (250 Hz up
to 300 Hz). Closer now sounds and looks different from further away - the alarm went from a single
bit of information to six.

**What it does not do:** the six-LED strip communicates "how close" well but nothing about "how
worried should I be", and it still reduces to noise and light with no record of what happened
without someone present to see it.

**Tester reaction (guard role):** the graduated tone was noticeably easier to judge by ear, but the
strip of LEDs "means something to whoever wired it, not to someone glancing at it for the first
time - I would not know what six lit-up LEDs is supposed to mean without being told."

**Change it caused:** feedback needs to be labelled, not just graded. → iteration 3.

---

## Iteration 3 - a labelled risk display

**Source:** Moodle Unit 21 practical, "Alarm System Three" (built in Tinkercad). Reproduced
verbatim.
**Built:** Arduino Uno + HC-SR04 + a 16x2 parallel LCD + four red LEDs + one green "safe" LED +
buzzer. Five named risk tiers (Extreme/High/Medium/Low/Safe) each print their own label to the LCD
alongside a distinct LED count and buzzer pattern.
**Wokwi:** https://wokwi.com/projects/475226849953199105
**Local copy:** `system_three/`

This is the most complete of the three official designs: a text readout removes the need to already
know what the LEDs mean, and the buzzer's rhythm (fast/slow, short/long) is distinct per tier so the
system communicates through two senses at once.

**What it does not do:** every one of the first three systems alarms on *presence*, not identity.
The guard doing their round, the cleaner at 6 a.m. and an actual intruder all produce the same
"Extreme Risk" reading, because the system has no way to tell them apart.

**Tester reaction (guard role):** the labelled display was the first version they said they would
actually trust at a glance, but they raised exactly the presence-versus-identity gap unprompted -
"this would go off on me every single round. After the third time I would stop looking at it, and
that is worse than not having it."

**Change it caused:** the system needs a way for an authorised person to identify themselves, so
that a legitimate entry is not treated as a threat at all. This is the point where the brief's own
scenario (a security company, not a driveway) starts to matter, and where the prototype stops being
a motion alarm and starts being an access-control system. → iteration 4.

---

## Iteration 4 - authenticate, do not just alarm

**Correction (2026-09-20):** this iteration was originally built and demonstrated with a 4x4
membrane keypad and a shared 4-digit PIN. It has since been rebuilt on an RFID card reader
(MFRC522) instead, kept on the same Uno + HC-SR04 + LCD parts family, because the keypad build
was independently wanted, unedited, as separate evidence for another end user's own submission
(see the Publishing status table). Presenting the same circuit as "the" iteration 4 in two
places at once would raise the same question the note at the end of this section already flags
for an even earlier keypad build - so the credential type changed, not the argument: an RFID tap
answers the presence-versus-identity gap System Three exposed for the same reasons, at the same
three named limitations below.

**Source:** this project's own design, built on top of the official baseline rather than supplied
by it. Everything above this line was given; everything in this iteration was designed to answer
the specific limitation iteration 3 exposed - see `PROMPT_rebuild_iterations.md` for the design
brief this was originally built against (written for the keypad version; the RFID rebuild answers
the same brief with a different credential, not a different problem).
**Built:** added an MFRC522 RFID reader and a 16x2 parallel LCD (six data/control lines, not
I2C, matching the brief's own System Three wiring). Approach within 80 cm now triggers a
"Present Card" prompt instead of a graded alarm; a recognised UID lights the green LED and shows
"Access Granted". Three deliberate design choices answer limitations named at iteration 3 and
earlier rather than being generic reader-and-alarm features:

- **The idle screen says "System Armed"** with the green LED held steady, so the board reads as
  "on and watching" rather than looking identical to powered-off - none of Systems One-Three make
  that distinction.
- **An unrecognised card warns before it locks.** Three unsuccessful presentations in a row
  trigger a short, clearly-communicated lockout (30 seconds, red LED, audible tone) rather than
  locking on the very first misread or unknown tap. This is a stated trade-off, not an
  afterthought: it costs some resistance to someone working through a stack of cards in exchange
  for not punishing one honestly misread tap of a legitimate badge.
- **The system stores a UID, not a person.** An RFID UID is not biometric data - UK GDPR's
  Article 9 rules for a face or fingerprint do not apply to it - and this design does not log
  which specific card was used or attach a name to an entry; it only checks list membership.
  That keeps it operationally equivalent to a shared PIN (valid/invalid, not who), which is a
  deliberate reason to keep this iteration here rather than reach for a camera or fingerprint
  sensor - see the privacy argument below.

**Wokwi:** https://wokwi.com/projects/475681794255610881
**Local copy:** `system_four/`

**Tester reaction (guard role):** the visible "Armed" idle state and the warning before lockout
read as a real access point rather than a demo circuit, the same reaction recorded against the
keypad version - swapping the credential did not change what made the design trustworthy to them.

**The limitation this iteration cannot fix on this hardware, which is why the Uno line ends here:**
the reader only checks whether a tapped UID is on a short whitelist; it does not record which
specific card was used or attach a name to an entry, so the log (Serial only, nothing persisted)
can show a recognised card was tapped but never *who* tapped it, and a lost card can only be
removed by reflashing the whole whitelist rather than revoking one entry. That is a genuine
limitation of a bare, unconnected Uno, not a property of RFID as a technology - the chip in a
card is capable of carrying a unique identity, but turning that into individual accountability
needs persistent storage, a reporting channel and a server-side roster this board does not have.
Fixing it needs a credential nobody else can produce *and* a system that remembers who used it -
a face, a fingerprint, a personal card checked against a live roster - and that is not a firmware
change on an ATmega328P. It is a different board, a camera or a networked reader, and a
recognition or roster pipeline. Iteration 5 is that change.

**Note on two earlier, separate builds:** a different keypad-and-lockout Arduino project
(https://wokwi.com/projects/474615233358282753) was built independently, before Systems One-Three
were identified as the official starting material; it was never presented as "the" iteration 4.
The keypad build that *was* presented as iteration 4 until 2026-09-20
(https://wokwi.com/projects/475228123420711937) has not been deleted either - it is kept,
unedited, as the version handed on as evidence for another end user's own, separate submission,
and should not also be presented as this project's iteration 4 alongside the RFID version above.
Only the RFID build at the URL given above is this report's fourth iteration.

---

## Iteration 5 - leaving the Uno: individual credentials on ESP32 (Charon)

**Source:** this project's own build, and a deliberate departure from the Uno line rather than
another sketch in it. This is real hardware, not a Wokwi simulation: six ESP32-S3-WROOM-1 boards,
each with an OV5640 camera, built and wired for this project, live and verified against a real
person on 03.09.2026.
**Built:** each node runs face detection and recognition (YuNet for detection, SFace for 128-d
embeddings, cosine similarity against enrolled staff) and reports to a FastAPI "brain" server that
holds the roster, the role/zone model (Guard, Worker, Visitor, Admin, IT across Reception,
Warehouse, Workshop and Server room) and the audit log. A live dashboard shows every node's state.
Repository: this project's GitHub repo (`charon-v2`).

**Why the board had to change, not just the code:** iteration 4's remaining objection has no fix on
an Arduino Uno. Telling *which* authorised person is at the door, rather than only "someone who
knows the code", needs a camera and enough processing power to run a recognition model in real
time - an 8-bit microcontroller with 2 KB of RAM cannot do this at all, not slowly, not
inconveniently, not at all. So the move to ESP32 is not scope creep; it is the direct, necessary
consequence of the limitation named at the end of iteration 4.

**Even the design of this iteration was corrected once before it was built.** The first proposal
(this project's own `DEMO_ARCHITECTURE` document) had a camera alone decide entry and exit. That was
rejected before a line of code was written: *"на воротах на вход/выход всё-таки считать что человек
вошёл, если прошёл мимо ультразвуковых сенсоров"* - at the gate, count someone as having actually
entered or exited only if they physically passed the ultrasonic sensors, not merely because a camera
recognised a face nearby. What got built instead is two separate signals that both have to agree:
recognition names someone and proposes a decision, but presence only commits when the passage
sensor's own counter increments. This is worth stating as its own micro-iteration because it shows
the pattern below repeating one level up: a design was proposed, a real limitation was named before
it shipped, and the design changed in response, exactly like iterations 1 through 4.

**What it does that iteration 4 could not:**
- **Individual accountability.** The audit log names a person, not "a valid code". One compromised
  or departing member of staff is removed on their own, without reissuing anything to the rest of
  the team.
- **Zone-aware, role-based access**, not just one door: the same recognition event can be checked
  against per-role, per-zone rules (a Visitor recognised at the Server room door is a different
  decision to a Guard recognised at Reception), which a shared keypad code has no way to express.
- **A continuous audit trail with names attached**, not an attempt counter.

**What it costs, which iteration 4 did not:** this is also where the privacy inversion in the D2
evaluation below actually bites. A face is biometric data under UK GDPR Article 9, which a PIN
never was. Every enrolled sample is special-category personal data with a lawful-basis and
retention-policy obligation attached, and getting that governance wrong is not a hypothetical risk
(section 3 of the accompanying report examines a real UK retail case where it went wrong). None of
Systems One through Four ever had to think about this, because none of them stored anything about a
person. Iteration 5 does, and the report's LO4 discussion exists largely because of this exact
trade.

**Two real problems surfaced on the same day it first went live, and were fixed the same day:**
camera frames were arriving upside down on some nodes (the per-node rotation setting was already
stored but nothing ever applied it - fixed by actually reading it), and the server was reachable
only from the machine running it (bound to `127.0.0.1`) until it was rebound to `0.0.0.0` so it could
be reached from a phone on the same network. Small fixes, but genuine same-day, feedback-driven
ones, not designed in advance.

**Tester reaction (guard/staff role):** recognising a face is one less thing to remember or leak - no
PIN to forget, share or have shoulder-surfed - and the welcome-by-name experience read as
noticeably more like a real staff entrance than a keypad. The same tester also asked, unprompted,
what happens if the camera gets something wrong: a fair question, and the honest answer is in the
report's discussion of the 19% real-world accuracy figure from the Metropolitan Police's own live
facial recognition trials (Fussey and Murray, 2019) - the same technology family, with a published,
sobering failure rate.

**Change it caused:** a working recognition system immediately raises the question of what happens
when it, or the network it depends on, fails outright - and what an intruder does with a shared
building once they realise a camera is what stands between them and the door. → iteration 6.

---

## Iteration 6 - the failover layer, and a design considered and declined

**Source:** this project's own build, 07.09.2026. Credential strengthened to two factors,
20.09.2026 (see below).
**Built:** a second Arduino Uno, wired as a standalone watchdog with an RFID reader, a 4-button
PIN pad, and its own EEPROM ring-buffer journal. It listens for a 1 Hz heartbeat from the ESP32
gate; if that heartbeat stops (the gate's ESP32 dies, loses WiFi, or the brain itself dies), the
Uno wakes and grants entry on a known RFID card *and* its matching PIN entered on four buttons,
logging every attempt - granted, denied, or right card/wrong PIN - into a ring buffer in its own
EEPROM. When the smart system recovers, the brain imports that journal and only then erases it -
never before the import is confirmed, so a second failure mid-import cannot lose the record.

**Correction (2026-09-20) - why the credential changed again:** iteration 4's own Uno prototype
moved from a keypad PIN to an RFID card (see its own correction note above), which took away the
distinction this section originally rested on - "iteration 4 is a keypad, this is a card reader".
Rather than pick a third, unrelated credential purely to look different on paper, this board's
credential was strengthened instead: it now asks for the card *and* a short PIN unique to that
card, entered on four buttons documented in `firmware/uno_watchdog/WIRING.md`. The reasoning in
`docs/REPORT_NOTES.md` sets out why this reads as a genuine improvement rather than a forced one -
a card alone is "something you have", clonable by anyone who reads its UID; the layer that only
gets used once every smarter system has already died is a reasonable place to require two factors
instead of one, not a coincidental way of avoiding a naming clash with iteration 4.

**Why this is not "iteration 4's card reader again":** it is tempting to see a second Uno with a
credential reader and assume it duplicates iteration 4. It does not, for two independent reasons.
First, role: iteration 4 is the primary, everyday access path; this Uno is a *last resort* that
exists only when everything smarter than it has already failed, and its one design requirement is
having no dependency that could fail alongside whatever it is standing in for. Second, strength:
iteration 4 checks one factor - a card - at a staffed, monitored, everyday entrance; this board
checks two - a card and a PIN unique to it - precisely because it is what stands between an
intruder and the building on the one night the smart system is actually down, with nobody
watching a screen to notice a bare-UID clone being tried.

**The idea proposed, and the reasoning for declining it:** the original instinct was to do better
than a static RFID card, which is clonable by anyone who learns its ID. The proposal on the table -
one-time codes sent to staff phones via Telegram whenever the smart system was healthy, pre-loaded
onto the Uno, rotating on every recovery - was recorded and evaluated seriously, not dismissed. It
fails for a reason that generalises: it depends on the very thing that is expected to have failed.
Of the three failures the layer exists for (the gate ESP32 dies, it loses WiFi, or the brain dies),
the brain dying is exactly the case with nobody left to send a code, and a recipient's phone needs
working network to receive one regardless. **Decision: keep RFID, add a PIN.** Rotation is the
right thing to want and the wrong thing to buy at the cost of the one property - needing no
network, no internet, no charged phone, no delivery - that makes a last line of defence
trustworthy; a fixed, per-card PIN raises the bar against a cloned card without giving up any of
those four properties. Recorded in full in `docs/REPORT_NOTES.md` because a rejected design with a
stated reason is stronger D-level evidence than a list of what shipped.

**What was corrected by real feedback on this same design:** the ring buffer's overflow behaviour
was originally going to stop recording once full. The actual instruction was the opposite - *"при
переполнениии пусть стирает старые записи"* (when it fills up, overwrite the oldest records) -
because reconciliation only ever cares about the outage that just happened, not a history of every
outage the journal has ever seen. Built the ring buffer that way, not the other way.

**Tester reaction (guard role):** a fallback that still recognises a physical card, the thing every
guard already carries for a dozen other doors, was the reassuring part - not a new procedure to
remember for the one night a year it might matter.

**Known limitation, named rather than hidden:** the Uno's card list is a mirror of who currently
holds a valid card and knows its PIN, hand-compiled rather than synced live, so it goes stale the
moment someone's access is revoked on the brain and nobody remembers to update the Uno too. This is recorded as a
limitation of the failover layer specifically, distinct from anything iterations 1-5 had to deal
with, because none of them had a second, disconnected store of the same information to fall out of
sync with.

**Change it caused:** having just made a real access decision (`require_admin`) harder to bypass by
accident everywhere else, the same day's testing found it had also made the one place it should not
apply - enrolling a person while sitting at the machine itself - annoyingly strict. → iteration 7.

---

## Iteration 7 - fixing the friction real use exposed

**Source:** this project's own build, 07.09.2026 (the same day as iteration 6, a different theme).

Two separate, real complaints, both fixed the day they were raised, both about how the system
behaves for the person actually operating it rather than about detection or security:

**"I tried to enrol today and it didn't work - it asked for the admin token."** Every mutating route
had correctly been put behind a shared admin token after A7 (admin authentication) was addressed,
which is the right default - but it made enrolling a person from the same Mac the server runs on
needlessly ceremonial, since anyone who can already reach that machine's `127.0.0.1` can read its
`.env` file or kill the process directly; a token prompt there adds friction, not protection. The
fix, confirmed explicitly rather than assumed: *"делай чтобы если открыл адрес страницы енрола, смог
енролить там. мне для презентации этого хватит."* Requests from `127.0.0.1` specifically (verified
by testing to be genuinely different from "anything on this Mac's LAN address", which arrives with a
different source address) are exempt; everything else still needs the token.

**A pre-shoot review the same day found two further real defects**, both small, both real: a dead
settings value that had no effect no matter what it was set to, and a credential file that had
leaked into a place the repository's own `.gitignore` should have caught. Both fixed and both worth
naming, because a habit of checking your own work for defects before a deadline, not only when a
user reports one, is itself part of the iteration story this file exists to tell.

**Tester reaction (operator role):** "enrol without a dance with a tambourine" was the literal
standard set for this fix, and it is the one this iteration is measured against - one click, from
the Mac, no prompt.

**Change it caused:** removing the admin-token barrier from local enrolment made it obvious that the
same convenience should not silently weaken anything reached from off the machine - which is
exactly the boundary the next iteration's own review had to re-examine under more adversarial
pressure. → iteration 8.

---

## Iteration 8 - a fix that created a defect, caught by review

**Source:** this project's own build, 08.09.2026 (the change) and 11.09.2026 (the review that caught
what it broke).

**What was fixed on 08.09:** recognition had been running directly on the event loop, which blocked
every other request - the dashboard, every other node's poll - for as long as a frame took to
process. Moving it into a thread pool executor fixed that; the loop's worst-case gap dropped to a
measured 1.9 ms.

**What that fix broke, reported honestly rather than hidden:** running directly on the event loop
had been serialising access to the shared OpenCV detector and recognizer by accident - only one
coroutine could ever be "in" that code at once, because nothing else could run while it did. Moving
recognition to an executor removed that accidental safety net: six pollers could now be inside the
same detector at the same moment, on a component library that does not promise that is safe.
`detect()` is two separate calls (`setInputSize()` then `detect()`), so two threads holding
differently-sized frames could genuinely interleave and have one detect at the other's dimensions.

**How it was caught:** a structured adversarial review before the shoot, run twice after the first
attempt hit session limits, found this along with six other real defects in one pass on 11.09 -
among them a policy clock comparing local-meaning working hours against a UTC clock (correct storage,
wrong comparison, would have silently admitted the wrong people at the wrong times on camera) and a
stale-pending-grant state left set after a denial. All eighteen findings from that review were
individually verified by hand rather than trusted at face value, because the review's own tooling
had already been caught silently mis-reporting one earlier defect as "unconfirmed" when it had never
actually been examined - a reminder that the process checking the system needs the same scepticism
applied to it, not only the system itself.

**The fix:** one lock around the shared detector, recognizer and roster, taken only for the fast
part (scoring against a snapshot), so an enrolment can still land without waiting on a whole frame
of recognition. Costs nothing the executor move was actually for: the loop stays free either way,
and the measured 1.9 ms gap is unaffected by the lock.

**Why this iteration is recorded even though nothing about it is user-facing:** M4 asks for
iteration based on feedback, and a structured review is a form of feedback - deliberately gathered,
adversarial, and in this case more effective than any single tester's live comment at finding a
defect that only shows up under concurrent load a casual walk-up test would never produce. Full list
of all seven defects and the reasoning for each is in `docs/REPORT_NOTES.md`; this entry is the one
worth telling live, because "the fix for one defect created a different one, and here is how it was
caught" is a stronger, more honest engineering story than a list of things that simply worked.

**Change it caused:** with the recognition path now correctly locked and the review's other six
findings fixed alongside it, the next real limitation to surface was not a defect at all but a
measured cost - how long a sleeping camera takes to be useful again. → iteration 9.

---

## Iteration 9 - camera always-on, recognition range instead of wake-on-approach

**Source:** this project's own build, 13.09.2026.
**Built:** iteration 5 kept each camera powered down until the near sensor reported someone within
250 cm, on the reasoning that an unpowered, non-recording camera is the strongest possible privacy
and energy story available. A 108-cycle bench soak on 03.09 confirmed the design was sound - no
failures, no reboot, no heap leak - and also measured its cost precisely: **median 937 ms from wake
to first usable frame.**

**Why that measurement argued the design out of the build:** that second is spent exactly when the
frames matter most - while the subject is still walking in - so the earliest frames the brain
actually received were of a face at an angle and mid-stride. The 250 cm trip distance existed only
to buy back that second of warm-up before the subject arrived. The design was solving a problem of
its own making.

**What replaced it:** the camera now initialises at boot and stays initialised. The near sensor no
longer switches anything on; it reports *recognition range*, tightened to 100 cm - roughly where an
approaching person is square-on to the camera and still moving slowly enough to yield a usable frame
- and the brain pulls a frame only while somebody is inside that range or an operator has explicitly
asked for one.

**The privacy argument survives the change and moves up a layer, which the report states rather than
glosses over:** data minimisation was never really "the camera is unpowered"; it is "nothing is
captured, processed or stored when the doorway is empty", and that is still true, now enforced by
the brain declining to request a frame rather than by the sensor cutting power. The honest
qualification: enforcement in software is weaker than enforcement in hardware, since a defect in the
brain could request a frame it should not, whereas an unpowered camera physically cannot produce
one.

**Cost accepted, stated rather than hidden:** holding the camera on costs roughly 23,400 B of heap
per node permanently, and removes the idle-power saving the sleeping design had. Both were judged
worth it for frames that are usable on the first attempt instead of the fifth.

**This is demo-only, by explicit choice, and is reversible.** The sleeping-camera design stays in
the report as the privacy-by-design and energy argument iteration 5 actually measured and validated;
it is not a fiction invented after the fact. Restoring it is a small, scoped change (the NVS-pinned
camera map is unaffected; only the recognition-range threshold and its wiring to `cam_on` change),
kept out only because a live demonstration benefits from every frame being usable rather than from
the extra second of energy and privacy story, which is fully documented either way.

**Tester reaction (operator role):** recognition landing on the first frame instead of needing a
second or third approach removed the one thing that had made the face-recognition demo feel
unreliable in rehearsal.

---

## Iteration 10 - the passage sensor loses its vote, and the report loses an argument

**Source:** this project's own build, 18.09.2026.
**Built:** iteration 5 fixed the gate on a two-beat model and every iteration since kept it.
Recognition names someone and issues a decision - green or red, the spoken line, the session token -
but presence only flips when the PASS ultrasonic's counter increments, because that is a real body
crossing the lane. The gap between the two beats is where this build found two anomalies the old
one had no events for at all: DENIED_CROSSED, recognised and refused and through the door anyway,
and UNIDENTIFIED_PASSAGE, a body crossing with no decision to bind it to.

**What real use exposed:** standing in front of a gate camera was enough to be recorded as having
entered or left, without going anywhere near the side-facing sensor. The obvious reading - that the
brain had started committing on the face alone - was wrong, and the audit log said so: the logic was
waiting for the sensor exactly as designed. The sensor was simply reporting crossings that were not
happening. **262 of the last 400 audit events were UNIDENTIFIED_PASSAGE**, and any one of them
landing inside the three-second bind window after a real recognition was enough to commit that
person.

**The measurement that settled it:** the PASS sonar at gate-in had **70% of its samples inside its
own 60 cm trip threshold** (median 33 cm), which means something was sitting permanently in front of
it and the sensor was resting in the BLOCKED state. A further **21% at gate-in and 34% at gate-out
read beyond 80 cm**, past the hysteresis release. Each of those excursions faked a clear, the next
normal reading re-blocked, and the pair was indistinguishable from a body passing. That produced
**34 and 59 phantom crossings in roughly three minutes** with nobody walking anywhere. Readings
jumping 20 → 153 → 30 cm between consecutive samples point at the second contributor: six
unsynchronised sonars on one bench hear each other's bursts.

**Why the defence already in place did nothing:** the hysteresis and two-sample agreement added
earlier were designed against the opposite failure - an idle-clear sensor whose noise fakes a
*block*. Here the resting state is inverted, so the same noise fakes a *clear*, and the guard sat on
the wrong side of the transition. A mitigation is only as good as the failure mode it was aimed at,
which is the more general lesson worth carrying out of this iteration.

**What replaced it:** `process_frame` now commits entry and exit itself, and the passage counter
decides nothing. The brain pulls frames only while the near sensor reports someone inside one metre,
so reaching a decision still means recognised *and* standing at the gate. Entry remains the only
direction a refusal can stop; exit stays fail-safe.

**What that costs, stated plainly rather than sold as a simplification:** both anomaly events are now
unreachable, because nothing independent of the face can disagree with the face. A decision and a
crossing became the same event, so the system can no longer notice that someone was recognised,
refused, and went through regardless - which was one of the two things this build had that its
predecessor did not. It also means a photograph held up to a gate camera commits an entry, where
previously it would at worst have produced a decision with no passage behind it.

**This contradicts the report, and the report has to carry that rather than quietly drop it.**
Section 2.2 argues that the answer to an indiscriminate sensor "is not to remove the sensor" but to
put a confirming layer behind it. Section 2.5 backs presence sensing "without reservation" on the
grounds that its risks are engineering risks and engineering risks can be engineered away. This
iteration is a measured counter-example to the second claim and an inversion of the first: the
confirming layer here is the camera, and it was the cheap sensor that had to be removed from the
decision path, not the expensive one. Both passages are qualified in the report accordingly.

**Reversible, and deliberately left so.** `process_passage` and its tests are untouched, because the
sensor is being abandoned for now rather than judged worthless. Remounted to face a clear lane, so
its resting state is genuinely clear, and with the edge test replaced by a dwell-time test - a
blocked period of plausible human length, then a sustained clear - it would restore both anomaly
events. Re-wiring it means removing the direct commit first, or every crossing is counted twice; the
module docstring says so at the point where someone would make that mistake.

**Operator observation (Marin, live testing):** appearing in front of either gate registered an entry
or an exit immediately, with the side sensors never involved. That report is what started this
iteration, and it is the only one in this log that began as a suspected fault in the recognition
path and ended in the sensor.

---

## D2 - evaluating the solution against their working practices

D2 asks for evaluation, which means the costs as well as the gains. A list of benefits alone reads as
a sales pitch and will not reach Distinction.

### What genuinely improves, iteration by iteration

| Working practice | Before (nothing built) | After iteration 4 (Uno, RFID card) | After iteration 9 (ESP32, current state) |
|---|---|---|---|
| Coverage of the entrance | Only while a guard is present | Continuous | Continuous |
| Nature of the alert | - | A labelled risk tier, then a credential check | A named recognition event |
| Authorisation decision | The guard, face to face | The system, on a shared credential | The system, on an individual credential |
| Accountability | None recorded | A recognised card was tapped (not by whom) | A named person was recognised |
| Social pressure on staff | Guard has to refuse colleagues personally | Removed - the reader refuses | Removed - the system refuses |
| Data the system holds about a person | None | None logged (a bare UID check, no name attached) | Biometric data (special category, Article 9) |
| What happens if the smart system dies | No fallback - the keypad itself is the only layer | Same | RFID failover on a second Uno, journalled and reconciled (iteration 6) |
| Response to its own defects | Fixed when a tester noticed | Same | A structured adversarial review, run twice, not just user reports (iteration 8) |

The accountability and data-held rows are the ones worth writing about at length, because together
they are the actual trade this project makes: the ESP32 line buys individual accountability by
taking on a data-protection obligation iterations 1-4 never had. That trade is exactly what D3 in
the report asks to be defended, not glossed over. The last two rows exist to show the evaluation is
not only about the sensor and the door - a mature access-control system also has to say what it does
when it fails and how it finds its own mistakes, and both are now answered rather than left as gaps.

### What it costs, and what it breaks

1. **False positives at a scale that makes a presence-only alert useless.** Measured twice: in
   principle across Systems One-Three (any ultrasonic trigger fires on anything that crosses it),
   and for real on the ESP32 gate (the 3,710-`unidentified_passage`-event figure in iteration 5).
   This is precisely why iteration 4 moved to authentication rather than tuning the threshold
   further, and why the ESP32 gate's own passage sensor needs the same fix rather than being
   trusted on its own.
2. **A shared, unlogged credential provides no individual accountability** (iteration 4's own
   limitation - first a PIN, now an RFID card checked against a bare whitelist - fixed from
   iteration 5 onward, at the cost below).
3. **Biometric data is a governance obligation a PIN never was** (iteration 5's own cost, see
   above and the report's LO4/D3 discussion).
4. **A lockout, wherever it exists, is a denial of service against legitimate staff.** Three
   fat-fingered attempts in the rain at 03:00 lock a guard out of their own building. Fail-secure on
   entry is the right default, but the cost falls on the honest user, not the attacker.
5. **Automation complacency.** A system that watches the door invites guards to stop watching it.
   The risk that operators disengage when automation appears reliable is well documented
   (Parasuraman and Riley, 1997).
6. **Single point of failure, until iteration 6.** Cut the power and the entrance has neither
   detection nor access control. The Uno watchdog layer built at iteration 6 exists precisely for
   this, and even it has a named limitation of its own (its card list is a hand-maintained mirror
   that can go stale against the brain's roster).
7. **A fix can create the defect it did not have before.** Iteration 8's own honestly-reported
   example: unblocking the event loop removed an accidental thread-safety guarantee nobody had
   designed in the first place. Worth stating plainly, because claiming every change only ever made
   things better would be the less credible story, not the more impressive one.

### The privacy argument, which runs the other way

For LO4 and D3 there is a genuinely interesting inversion here: the *simpler*, earlier iteration is
the more defensible one under data protection law. Iterations 1-4 store no personal data at all - a
PIN was a shared secret, and an RFID UID is neither biometric nor logged against a name in this
design, so UK GDPR Article 9 does not apply to any of them and there is no special-category
processing to justify. Iteration 5 onward, which is where the
accountability problem actually gets solved, is where the system starts carrying a DPIA obligation,
a retention policy and a lawful-basis argument. That trade-off between accountability and privacy is
exactly the kind of thing D3 asks you to defend rather than dodge, and it only exists because the
project did not stop at iteration 4.

---

## Publishing status

| Iteration | What it is | Where it lives |
|---|---|---|
| 1 - buzzer alarm | Moodle "Alarm System One", reproduced | https://wokwi.com/projects/475226607766686721 |
| 2 - graduated LED/tone | Moodle "Alarm System Two", reproduced | https://wokwi.com/projects/475226727289705473 |
| 3 - LCD risk display | Moodle "Alarm System Three", reproduced | https://wokwi.com/projects/475226849953199105 |
| 4 - RFID access control | This project's own design, on the required Uno (rebuilt from a keypad, 20.09) | https://wokwi.com/projects/475681794255610881 |
| 5 - face recognition (Charon) | This project's own build, real hardware, ESP32 | this repository, commits `c065a03`-`da6d3a8` (03.09) |
| 6 - RFID + PIN failover layer | Second Uno, watchdog + journal, real hardware; PIN second factor added 20.09 | this repository, commits `48a8116`-`77b619a` (07.09), PIN update 20.09 |
| 7 - operational fixes from real use | Loopback-exempt enrolment, two-defect review | this repository, commits `ce0f6af`, `002316e` (07.09) |
| 8 - a fix that broke something, caught by review | Event-loop unblock, then a thread-safety fix | this repository, commits `ff46a4c` (08.09), `6941e8e` (11.09) |
| 9 - camera always-on | Recognition range replaces wake-on-approach | this repository, commit `b0ee2a2` (13.09) |
| 10 - passage sensor loses its vote | Measured sensor failure; recognition commits alone | this repository (18.09) |

Full detail behind iterations 5-9, including the six other defects iteration 8's review found and
the measurements behind iteration 9, is in `docs/REPORT_NOTES.md` - this file tells the arc each one
belongs to; that one carries the numbers.

Iteration 4 must not be edited casually - it is the version presented as the answer to iteration 3.
As of 2026-09-20 that is the RFID build (`https://wokwi.com/projects/475681794255610881`), not the
keypad build kept alongside it for a different end user's own submission (see Publishing status).
Iterations 1-3 are reproductions of the official material and should stay byte-for-byte faithful to
it; if they ever need rebuilding, `system_one/`, `system_two/`, `system_three/` and `system_four/`
each hold the exact `sketch.ino` and `diagram.json` that were pasted in and saved.

If any of iterations 1-4 ever need rebuilding from scratch: open a new project at
https://wokwi.com/projects/new/arduino-uno, paste `sketch.ino` over the default sketch, click the
`diagram.json` tab and paste that file over what is there, then Save (Public) and name it. Note that
Wokwi's live circuit preview sometimes does not repaint until you switch away from the diagram.json
tab and back, or until the project is actually saved - an empty-looking preview while editing is not
evidence the diagram is wrong.

## Reference

Fussey, P. and Murray, D. (2019) *Independent Report on the London Metropolitan Police Service's
Trial of Live Facial Recognition Technology*. Colchester: University of Essex Human Rights Centre.

Parasuraman, R. and Riley, V. (1997) 'Humans and automation: use, misuse, disuse, abuse',
*Human Factors*, 39(2), pp. 230-253.
