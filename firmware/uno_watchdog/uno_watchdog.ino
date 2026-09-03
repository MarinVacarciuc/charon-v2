/*
  Charon Layer 3 - the gate's independent failover watchdog.

  This board is deliberately the stupid one. It has no network, no camera, no clock, and no
  idea who anyone is. It watches a single wire and answers one question: is the smart system
  still alive? When the answer becomes no, it takes the gate over on its own terms - presence,
  not identity - so the perimeter keeps working after everything clever has failed.

  That is the whole argument of the demo's last beat, and it is why the two brains are
  deliberately of different intelligence: a smart one that can be killed, and a dumb one that
  cannot. Defence in depth made literal rather than described.

  WIRING (gate-in ESP32-S3 and this Uno share a power bank, so they share a ground):
    D2   <- heartbeat from gate-in GPIO 21. 3.3 V into a 5 V-tolerant input, one direction
            only. NEVER wire the reverse: 5 V into an ESP32 GPIO destroys it.
    GND  <- common ground with the ESP. Without this the heartbeat has no reference and the
            input floats, which reads as a fast random square wave: the failure looks like a
            heartbeat, which is the worst possible failure mode here.
    D5/D6 -> own RCWL-1601 (trig/echo). 3.3 V logic, safe on a 5 V Uno input.
    D8   -> green LED via ~330R    (pass)
    D9   -> red LED via ~330R      (armed / smart path down)
    D10  -> buzzer                 (short chirp on a pass; the brief asks for an alarm)

  The heartbeat is a ~1 Hz SQUARE WAVE, not a level, and that choice matters: a wire that
  comes loose, or a board that dies with its pin held high, would satisfy a level check
  forever. Only something actively alive can keep toggling.
*/

// ---- pins ----
const uint8_t PIN_HB    = 2;   // must be 2 or 3 on an Uno: the only external-interrupt pins
const uint8_t PIN_TRIG  = 5;
const uint8_t PIN_ECHO  = 6;
const uint8_t PIN_GREEN = 8;
const uint8_t PIN_RED   = 9;
const uint8_t PIN_BUZZ  = 10;

// ---- timings ----
// Three missed beats before declaring the smart path down. One missed beat is noise; this is
// the same "two agreeing readings" discipline the ESP uses on its ultrasonics, applied to a
// wire. Long enough not to twitch, short enough that the takeover is visibly prompt on camera.
const unsigned long HB_TIMEOUT_MS   = 3000;
const unsigned long PASS_HOLD_MS    = 4000;   // how long "pass" stays lit once triggered
const unsigned long BUZZ_MS         = 120;
const unsigned long SONAR_PERIOD_MS = 60;

// ---- ultrasonic thresholds ----
// Same hysteresis idea as the node firmware, for the same measured reason: a single trip
// distance flips back and forth on noise near the boundary, and on a cluttered surface the
// readings genuinely swing across a metre or more. Trip close, clear only when unambiguously
// clear, and require two agreeing readings before believing either.
const int   TRIP_CM = 120;
const int   HYST_CM = 25;
const uint8_t AGREE_NEEDED = 2;

// ---- heartbeat state ----
// Written from an interrupt, read from loop(): must be volatile, and must be read with
// interrupts briefly disabled, because an unsigned long is four bytes on an 8-bit AVR and a
// non-atomic read can catch it half-updated - a garbage timestamp here would fake a healthy
// system or a dead one at random.
volatile unsigned long lastBeatMs = 0;
volatile bool everBeat = false;

bool smartPathUp = false;
bool announced   = false;

// ---- sonar state ----
float lastCm = -1;
bool  blocked = false, cand = false;
uint8_t agree = 0;
unsigned long passUntil = 0, buzzUntil = 0, lastPingMs = 0;

void onHeartbeat() {
  // An interrupt rather than polling: loop() spends up to 25 ms inside pulseIn() waiting for
  // an echo, and polling would drop edges during exactly the window when knowing the smart
  // path is alive matters most.
  lastBeatMs = millis();
  everBeat = true;
}

unsigned long beatAge() {
  noInterrupts();
  unsigned long t = lastBeatMs;
  bool seen = everBeat;
  interrupts();
  if (!seen) return HB_TIMEOUT_MS + 1;   // never heard one: treat as down, do not assume health
  return millis() - t;
}

float readDistanceCm() {
  digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(3);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long us = pulseIn(PIN_ECHO, HIGH, 25000UL);   // ~4 m ceiling; 0 = no echo
  return us ? us / 58.0f : -1.0f;
}

// Returns true on the rising edge of "someone is there".
bool pollSonar() {
  lastCm = readDistanceCm();
  bool nowBlocked = blocked
      ? !(lastCm <= 0 || lastCm > TRIP_CM + HYST_CM)
      : (lastCm > 0 && lastCm < TRIP_CM);
  if (nowBlocked == cand) { if (agree < AGREE_NEEDED) agree++; }
  else { cand = nowBlocked; agree = 1; }
  if (agree >= AGREE_NEEDED && cand != blocked) {
    blocked = cand;
    return blocked;
  }
  return false;
}

void setup() {
  pinMode(PIN_HB, INPUT);          // the ESP drives this actively; no pull-up, or a floating
                                   // wire would be pulled to a steady level and look sane
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_GREEN, OUTPUT);
  pinMode(PIN_RED, OUTPUT);
  pinMode(PIN_BUZZ, OUTPUT);
  digitalWrite(PIN_TRIG, LOW);
  digitalWrite(PIN_GREEN, LOW);
  digitalWrite(PIN_RED, LOW);
  digitalWrite(PIN_BUZZ, LOW);

  attachInterrupt(digitalPinToInterrupt(PIN_HB), onHeartbeat, CHANGE);

  Serial.begin(9600);
  Serial.println(F("[uno] charon gate watchdog"));
  Serial.println(F("[uno] watching heartbeat on D2; independent of network and laptop"));
  // Printed state changes are the artefact: a screen recording of this serial output is what
  // shows the takeover happening, and the timestamps are what the latency measurement reads.
  Serial.println(F("[uno] state,millis,detail"));
}

void loop() {
  unsigned long now = millis();
  bool up = beatAge() < HB_TIMEOUT_MS;

  if (up != smartPathUp || !announced) {
    smartPathUp = up;
    announced = true;
    if (up) {
      Serial.print(F("SMART_UP,"));   Serial.print(now);
      Serial.println(F(",heartbeat present - standing down"));
      digitalWrite(PIN_RED, LOW);
    } else {
      Serial.print(F("SMART_DOWN,")); Serial.print(now);
      Serial.println(F(",no heartbeat - this board now owns the gate"));
      digitalWrite(PIN_RED, HIGH);    // armed, and visibly so
      // Re-arm the sonar state machine so a person already standing there when the smart path
      // dies still produces a fresh rising edge rather than being missed as "already blocked".
      blocked = false; cand = false; agree = 0;
    }
  }

  if (now - lastPingMs >= SONAR_PERIOD_MS) {
    lastPingMs = now;
    bool arrived = pollSonar();
    // Only acts while the smart path is down. With the brain alive this board stays quiet on
    // purpose: two systems deciding the same gate at once is worse than either alone.
    if (arrived && !smartPathUp) {
      Serial.print(F("PASS,")); Serial.print(now);
      Serial.print(F(",presence at ")); Serial.print(lastCm, 0); Serial.println(F("cm - opening"));
      passUntil = now + PASS_HOLD_MS;
      buzzUntil = now + BUZZ_MS;
    }
  }

  // Green is driven by its own hold rather than being cut the instant the brain returns: a
  // person mid-walk-through should not have the light yanked out from under them.
  digitalWrite(PIN_GREEN, (long)(passUntil - now) > 0 ? HIGH : LOW);
  digitalWrite(PIN_BUZZ,  (long)(buzzUntil - now) > 0 ? HIGH : LOW);
}
