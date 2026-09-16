# Iteration log: one access-control system, five iterations

Unit 21 *Emerging Technologies*, scenario **Ezra and Korede Security Ltd**.
This file exists to satisfy two criteria a finished circuit cannot satisfy on its own:

* **M4** - *Make multiple iterations of your solution based on feedback gathered from a given end-user group.*
* **D2** - *Evaluate the solution developed including its impact on a given end-user group and their current systems and working practices.*

The brief is explicit that the demonstration has to "show each iteration ... discussing feedback
received and specific changes made to the system as a result of the feedback received". A single
polished final build is worth P4 and no more.

**This is one system, not two.** Iterations 1-4 were built on an Arduino Uno because that is the
brief's mandatory starting point (P5). Iteration 5 is not a separate, parallel project presented
alongside the Arduino work for comparison - it is what the Uno line grew into once its own limits
were reached. The Uno was left behind deliberately, for a stated reason (below), and everything it
could not do is exactly what iteration 5 exists to do. The demonstration and the report should both
tell this as a single continuous line: four iterations on the required hardware, then a fifth that
moved off it once the requirement had been met and outgrown.

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

**Source:** this project's own design, built on top of the official baseline rather than supplied
by it. Everything above this line was given; everything in this iteration was designed to answer
the specific limitation iteration 3 exposed - see `PROMPT_rebuild_iterations.md` for the design
brief this was built against.
**Built:** added a 4x4 membrane keypad and a 16x2 I2C LCD. The system is a state machine:
`SYS_IDLE → CODE_ENTRY → GRANTED` or `→ LOCKED_OUT`. Approach now triggers a code prompt instead of
a graded alarm; digits are masked with `*` on the LCD; a correct code lights the green LED and shows
a welcome message. Three deliberate design choices answer limitations named at iteration 3 and
earlier rather than being generic keypad-alarm features:

- **The idle screen says "System Armed"** with the green LED held steady, so the board reads as
  "on and watching" rather than looking identical to powered-off - none of Systems One-Three make
  that distinction.
- **A wrong code warns before it locks.** The second wrong attempt gets an explicit "Last attempt!"
  message and a two-beep warning rather than silently counting down to a lockout; only the third
  wrong attempt actually locks the keypad, for 20 seconds, with a live countdown on the LCD. This is
  a stated trade-off, not an afterthought: it costs some resistance to a determined attacker in
  exchange for not punishing one honestly mistyped PIN.
- **The system stores a PIN, not a person.** No biometric data is captured anywhere in this design,
  which is a deliberate reason to keep this iteration on a shared secret rather than reach for a
  camera or fingerprint sensor - see the privacy argument below.

**Wokwi:** https://wokwi.com/projects/475228123420711937
**Local copy:** `system_four/`

**Tester reaction (guard role):** the masked PIN entry, the visible "Armed" idle state and the
warning before lockout read as a real access point rather than a demo circuit - the first version
they said they would leave switched on unattended.

**The limitation this iteration cannot fix on this hardware, which is why the Uno line ends here:**
everyone uses the same code, so the log can show a valid code was entered but never *who* entered
it, and a leaked code can only be revoked for the whole team at once. That is a genuine limitation
of a shared-secret keypad, not an oversight. Fixing it needs a credential nobody else can produce -
a face, a fingerprint, a personal card - and that is not a firmware change on an ATmega328P. It is a
different board, a camera, and a recognition pipeline. Iteration 5 is that change.

**Note on an earlier, separate build:** a different keypad-and-lockout Arduino project
(https://wokwi.com/projects/474615233358282753) was built independently, before Systems One-Three
were identified as the official starting material. It covers similar ground but was not designed as
an explicit answer to System Three's stated limitation, so System Four above is the version this
report and demonstration should present as the fourth iteration. The earlier build is not deleted
and remains usable as extra evidence of iteration if needed, but the two should not both be
presented as "the" iteration 4 in the same document - it invites the question of which one is real.

---

## Iteration 5 - leaving the Uno: individual credentials on ESP32 (Charon)

**Source:** this project's own build, and a deliberate departure from the Uno line rather than
another sketch in it. This is real hardware, not a Wokwi simulation: six ESP32-S3-WROOM-1 boards,
each with an OV5640 camera, built and wired for this project.
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

**The same structural problem Systems One-Three had, now measured on real hardware:** presence-only
detection does not survive contact with a real doorway. The ultrasonic passage sensor on the live
ESP32 gate logged **3,710 `unidentified_passage` events** across three days of testing (22 on
03.09, 1,293 on 07.09, 2,395 on 08.09), against genuine traffic on the busiest of those days of:

| 08.09.2026 | Count |
|---|---|
| `unidentified_passage` (sensor fired, nobody identified) | 2,395 |
| `entry` (a real person actually went in) | 7 |
| `exit` (a real person actually went out) | 3 |

Roughly 240 sensor events for every real movement. Systems One through Three predicted this in
principle (an ultrasonic trigger cannot distinguish a person from anything else that crosses it);
iteration 5 is where it was actually measured, on the same class of sensor, at a much larger scale
than a benchtop test could show. This is the throughline the demonstration should make explicit:
the Uno builds diagnosed the disease, the ESP32 build is where its full size became visible.

**Tester reaction (guard/staff role):** recognising a face is one less thing to remember or leak - no
PIN to forget, share or have shoulder-surfed - and the welcome-by-name experience read as
noticeably more like a real staff entrance than a keypad. The same tester also asked, unprompted,
what happens if the camera gets something wrong: a fair question, and the honest answer is in the
report's discussion of the 19% real-world accuracy figure from the Metropolitan Police's own live
facial recognition trials (Fussey and Murray, 2019) - the same technology family, with a published,
sobering failure rate.

**This file stops here on purpose.** Iteration 5 itself went through further, smaller iterations
after it was first built (the camera's power/wake model changed on 13.09.2026, for a stated
measured reason; gate and zone logic were each revised at least once) - that history belongs to
`docs/REPORT_NOTES.md` and the project's own commit history, not duplicated here. This file's job is
the arc from a bare ultrasonic buzzer to a named face at a door; the fine-grained engineering
history of the ESP32 build once it existed is recorded where the rest of that build's evidence
already lives.

---

## D2 - evaluating the solution against their working practices

D2 asks for evaluation, which means the costs as well as the gains. A list of benefits alone reads as
a sales pitch and will not reach Distinction.

### What genuinely improves, iteration by iteration

| Working practice | Before (nothing built) | After iteration 4 (Uno, keypad) | After iteration 5 (ESP32, face) |
|---|---|---|---|
| Coverage of the entrance | Only while a guard is present | Continuous | Continuous |
| Nature of the alert | - | A labelled risk tier, then a credential check | A named recognition event |
| Authorisation decision | The guard, face to face | The system, on a shared credential | The system, on an individual credential |
| Accountability | None recorded | A valid code was used (not by whom) | A named person was recognised |
| Social pressure on staff | Guard has to refuse colleagues personally | Removed - the keypad refuses | Removed - the system refuses |
| Data the system holds about a person | None | None (a PIN is not personal data) | Biometric data (special category, Article 9) |

The accountability and data-held rows are the ones worth writing about at length, because together
they are the actual trade this project makes: iteration 5 buys individual accountability by taking
on a data-protection obligation iterations 1-4 never had. That trade is exactly what D3 in the
report asks to be defended, not glossed over.

### What it costs, and what it breaks

1. **False positives at a scale that makes a presence-only alert useless.** Measured twice: in
   principle across Systems One-Three (any ultrasonic trigger fires on anything that crosses it),
   and for real on the ESP32 gate (the 3,710-event figure above). This is precisely why iteration 4
   moved to authentication rather than tuning the threshold further, and why iteration 5's own
   passage sensor needs the same fix rather than being trusted on its own.
2. **A shared PIN provides no individual accountability** (iteration 4's own limitation, fixed by
   iteration 5, at the cost below).
3. **Biometric data is a governance obligation a PIN never was** (iteration 5's own cost, see
   above and the report's LO4/D3 discussion).
4. **A lockout, wherever it exists, is a denial of service against legitimate staff.** Three
   fat-fingered attempts in the rain at 03:00 lock a guard out of their own building. Fail-secure on
   entry is the right default, but the cost falls on the honest user, not the attacker.
5. **Automation complacency.** A system that watches the door invites guards to stop watching it.
   The risk that operators disengage when automation appears reliable is well documented
   (Parasuraman and Riley, 1997).
6. **Single point of failure.** Cut the power and the entrance has neither detection nor access
   control, at any iteration. The Uno watchdog layer designed for the ESP32 system exists precisely
   for this - itself an example of the same "what does this iteration not do yet" logic applied one
   level up, at the level of the whole system rather than one board.

### The privacy argument, which runs the other way

For LO4 and D3 there is a genuinely interesting inversion here: the *simpler*, earlier iteration is
the more defensible one under data protection law. Iterations 1-4 store no personal data at all - a
PIN is a shared secret, not biometric data, so UK GDPR Article 9 does not apply to any of them and
there is no special-category processing to justify. Iteration 5, which is the one that actually
solves the accountability problem, is the one that carries a DPIA obligation, a retention policy and
a lawful-basis argument. That trade-off between accountability and privacy is exactly the kind of
thing D3 asks you to defend rather than dodge, and it only exists because the project did not stop
at iteration 4.

---

## Publishing status

| Iteration | What it is | Where it lives |
|---|---|---|
| 1 - buzzer alarm | Moodle "Alarm System One", reproduced | https://wokwi.com/projects/475226607766686721 |
| 2 - graduated LED/tone | Moodle "Alarm System Two", reproduced | https://wokwi.com/projects/475226727289705473 |
| 3 - LCD risk display | Moodle "Alarm System Three", reproduced | https://wokwi.com/projects/475226849953199105 |
| 4 - keypad access control | This project's own design, on the required Uno | https://wokwi.com/projects/475228123420711937 |
| 5 - face recognition (Charon) | This project's own build, real hardware, ESP32 | this repository |

Iteration 4 must not be edited casually - it is the version presented as the answer to iteration 3.
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
