# Field day runbook

Follow this in order. Each step has a check, so a mistake is caught where it was made.

Yard time is the scarcest thing left, so the order is by **what the video actually needs**,
not by tidiness. If you run out of daylight, stop wherever you are - the steps below the line
in section 2 are the ones that cost you nothing to skip.

Open the dashboard on your phone before you start: `run.sh` prints the address.

---

## 0. Before going outside (5 min, indoors)

- [ ] Hotspot on, laptop joined to it.
- [ ] `cd ~/IdeaProjects/charon-v2/server && ./run.sh` - leave the window open.
- [ ] All six boards showing on the dashboard node strip.
- [ ] Every board **off USB and on a battery bank**. A board on USB was measured flapping its
      WiFi every 8-90 seconds; it will waste your afternoon looking like a network fault.

---

## 1. Priority order for mounting

Mount in this order. Each of the first four carries a filmed beat; the last two carry none.

| Order | Node | Where | Beat it carries |
|---|---|---|---|
| 1 | `gate-in` | the gate, facing whoever walks up | 1, 2 and 7 - the whole opening and the ending |
| 2 | `zone-reception` | first place you walk into | 3 |
| 3 | `zone-server` | the "server room" spot | 5 - the refusal, the strongest shot |
| 4 | `zone-workshop` | the workshop spot | 6 - the just-in-time pass |
| --- | --- | --- | --- |
| 5 | `gate-out` | the gate, facing outward | none directly |
| 6 | `zone-warehouse` | the warehouse spot | none directly |

**If the light goes, stop after 4.** Nothing above the line depends on the two below it.

---

## 2. For each board, in this order

### a) Position it

Two things decide whether recognition works, and neither is software:

- **Never point a camera at the bright sky or an open doorway.** A backlit face becomes a
  silhouette, the embedding is close to noise, and the best match then bounces between
  enrolled people at random. Put the light behind the camera, not behind the face.
- Mount at roughly face height for someone walking up, not looking down from above. A steep
  downward angle is the second most common reason a face stops being recognised.

### b) Check it is on the network, from where it now is

On your phone, dashboard node strip: the chip for this node should read `LIVE` or
`ARMED · camera off`. If it reads `OFFLINE`, the hotspot does not reach this spot - move the
hotspot phone, not the board.

### c) Fix the picture orientation

Look at this node's tile at the bottom of the dashboard. Upside down or sideways? Hover the
tile and press the **⟳** button until it is right. It is saved per node and survives a restart.

### d) Calibrate the sensors **here**, not on a desk

This is the step that cannot be done indoors. On a cluttered desk the readings were measured
swinging between 33 and 233 cm with nothing moving - that is multipath, and no software filter
fixes it. The number is only meaningful at the final mounted position.

Open **Settings** on your phone. For this node the "wake distance" field shows the live
reading as its placeholder.

1. Stand where a person would be when the camera should wake. Read the live number.
2. Walk away. Read the number again with nobody there.
3. Set **wake distance** comfortably between the two - nearer to the empty reading than to
   the person, so ordinary clutter does not trip it.
4. For `gate-in` and `gate-out` only, do the same for **passage distance**: stand *in* the
   lane, read; clear the lane, read; set it between.
5. Press **Apply**. The value is stored on the board itself, so it survives a flat battery.

**Check:** walk up to the node and away from it a few times. The tile should wake and go to
sleep. For the gate, `/nodes` passage count should rise by exactly one per crossing - not two,
not none.

---

## 3. Enrol the cast (do this LAST, once everything is mounted)

Enrolment has to happen **in the yard, in the light you will film in**. Samples taken indoors
under different light are the single most common reason a face stops being recognised on the
day.

Per person, on the **Staff** page:

1. Choose the camera explicitly - start with `gate-in`.
2. Name and role. From the beat sheet: Marin is `GUARD`, the IT person is `IT`, the admin is
   `ADMIN`, the visitor is `VISITOR`.
3. Capture, then **capture again three or four more times**: head straight on, turned slightly
   left, slightly right, chin a little down. Each capture adds a sample and the system matches
   against the best of them.
4. Then capture **two more at `zone-server`**, because that spot's light is different and it
   is where the refusal beat happens.

**Check, per person:** stand in front of `gate-in` and open
`/people/recognise?node=gate-in` on your phone. You want `confident: true` and a score
comfortably above 0.45 - typically 0.6 to 0.9. If it sits at 0.45 to 0.55, add more samples
from that spot rather than hoping.

Leave the stranger for beat 5 **unenrolled**. That is the point of them.

---

## 4. Final walk-through before you stop

With everything mounted, calibrated and enrolled, walk the whole route once and watch the
dashboard on your phone:

- [ ] Walk to `gate-in` - terminal goes green, your name, voice speaks, Telegram arrives.
- [ ] Cross the lane - you appear on the board as on site.
- [ ] Walk into Reception - your card moves to the Reception column.
- [ ] Walk into the Server room - a loud red alert, voice refuses, phone buzzes.
- [ ] Press **Reset take** on the dashboard - the board empties and everything is ready to run
      again.

If all five behave, the shoot is a filming problem rather than an engineering one.

---

## If something is wrong

| Symptom | Almost certainly |
|---|---|
| Node `OFFLINE` in one spot only | hotspot does not reach there |
| All nodes offline at once | hotspot dropped, or the laptop left the hotspot |
| Recognised indoors, not outdoors | enrolled in the wrong light - add samples on the spot |
| Score stuck around 0.4 | backlit, or camera angled too steeply down |
| Passage counts twice per crossing | passage distance set too far - lower it |
| Camera never wakes | wake distance set too near - raise it |
| A board flaps on and off | it is on USB power - move it to a battery |
