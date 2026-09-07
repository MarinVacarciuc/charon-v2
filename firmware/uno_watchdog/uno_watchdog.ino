/*
  Charon Layer 3 - the gate's independent failover.

  This board is deliberately the stupid one. No network, no camera, no clock, no idea who
  anyone is beyond a number on a card. It watches a single wire to answer one question - is
  the smart system still alive? - and when the answer becomes no, it takes the gate over on
  its own terms.

  That is the argument of the demo's last beat, and it is why the two brains are deliberately
  of different intelligence: a clever one that can be killed, and a dumb one that cannot.

  WHAT CHANGED WHEN RFID ARRIVED, AND WHY IT MATTERS
  The first version opened on presence alone: during an outage, anyone who walked up got in.
  That is a poor thing to call a security feature, and it contradicts the fail-secure posture
  the brief asks for on an entry lane. Now a card is what opens the gate, and the ultrasonic
  keeps a different, better job: noticing that somebody approached, so an approach with NO
  card presented is recorded rather than silently ignored.

  Degrading from "who you are" to "what you carry" is the honest trade. The system loses
  convenience and gains nothing it did not have; it does not lose the ability to say no.

  WIRING (the Uno and gate-in share a power bank, so they share a ground)
    D2   <- heartbeat from gate-in GPIO 21. 3.3 V into a 5 V-tolerant input, ONE DIRECTION.
            Never wire the reverse: 5 V into an ESP32 GPIO destroys it.
    GND  <- common ground with the ESP. Without it the input floats, and a floating input
            reads as a fast random square wave - which looks exactly like a healthy
            heartbeat. That is the worst failure this board can have, so check it first.
    D3   -> MFRC522 RST
    D5   -> RCWL-1601 TRIG        D6 <- RCWL-1601 ECHO
    D7   -> buzzer                (moved off D10, which SPI needs)
    D8   -> green LED via ~330R   D9 -> red LED via ~330R
    D10  -> MFRC522 SDA/SS        D11 -> MOSI    D12 <- MISO    D13 -> SCK
    MFRC522 VCC -> 3.3 V, NOT 5 V. Its logic tolerates the Uno's 5 V signalling, its supply
    does not.
*/
#include <SPI.h>
#include <EEPROM.h>
#include <MFRC522.h>
#include "cards.h"

// ---- pins ----
const uint8_t PIN_HB    = 2;   // must be 2 or 3: the only external-interrupt pins on an Uno
const uint8_t PIN_RFID_RST = 3;
const uint8_t PIN_TRIG  = 5;
const uint8_t PIN_ECHO  = 6;
const uint8_t PIN_BUZZ  = 7;
const uint8_t PIN_GREEN = 8;
const uint8_t PIN_RED   = 9;
const uint8_t PIN_RFID_SS = 10;

// ---- timings ----
// Three missed beats before declaring the smart path down. One missed beat is noise; this is
// the same "two agreeing readings" discipline the ESP uses on its ultrasonics, applied to a
// wire. Long enough not to twitch, short enough to be visibly prompt on camera.
const unsigned long HB_TIMEOUT_MS    = 3000;
const unsigned long PASS_HOLD_MS     = 4000;
const unsigned long DENY_HOLD_MS     = 2000;
const unsigned long BUZZ_MS          = 120;
const unsigned long SONAR_PERIOD_MS  = 60;
const unsigned long SAME_CARD_MS     = 3000;   // ignore a card held against the reader
const unsigned long APPROACH_WAIT_MS = 8000;   // approach with no card within this = recorded

// ---- ultrasonic ----
const int TRIP_CM = 120;
const int HYST_CM = 25;
const uint8_t AGREE_NEEDED = 2;

MFRC522 rfid(PIN_RFID_SS, PIN_RFID_RST);

// ---- heartbeat state (written in an ISR) ----
volatile unsigned long lastBeatMs = 0;
volatile bool everBeat = false;

bool smartPathUp = false, announced = false;

// ---- sonar state ----
float lastCm = -1;
bool blocked = false, cand = false;
uint8_t agree = 0;

unsigned long passUntil = 0, denyUntil = 0, buzzUntil = 0, lastPingMs = 0;
unsigned long approachAt = 0;           // 0 = nobody currently waiting unidentified
char lastUid[32] = "";
unsigned long lastUidAt = 0;


/* ------------------------------------------------------------------ failover journal

   Everything this board decides happens while the brain is unreachable by definition, so
   nothing it does would otherwise be recoverable afterwards. The journal is what turns
   "the brain will never know who came in" into "the brain finds out at the next check".

   EEPROM rather than an SD card, for a reason worth stating: the data has to be written by
   the board that KNOWS the event, and that is this one - the card reader is here, not on the
   ESP32. An SD card on the ESP32 would sit there recording nothing, because the ESP is on
   the far side of a one-way wire and, in the demo's own scenario, is the thing being killed.
   The Uno already has 1 KB of non-volatile storage built in, which is more than a hundred
   records; no extra hardware, no extra pins, nothing more to solder or fail.

   Timestamps are seconds since THIS BOARD booted, because it has no clock. That is honest and
   sufficient: the brain knows when the outage began, and the offsets place the events inside
   it.

   A ring buffer: when it fills, the oldest records are overwritten. Reconciliation is about
   the outage happening NOW, so the newest records are the ones worth keeping, and records
   from sessions long past are noise. The dump reports that wrapping happened, so a full
   journal is never mistaken for a complete one. */

const uint16_t EE_MAGIC_ADDR = 0;      // 2 bytes: marks the journal as ours and initialised
const uint16_t EE_HEAD_ADDR  = 2;      // 1 byte : next slot to write
const uint16_t EE_FLAGS_ADDR = 3;      // 1 byte : bit0 = has wrapped at least once
const uint16_t EE_DATA_ADDR  = 4;
const uint16_t EE_MAGIC      = 0x4348; // 'CH'
const uint8_t  REC_SIZE      = 9;      // 4 uid + 4 seconds + 1 outcome
const uint8_t  EE_CAPACITY   = (uint8_t)((1024 - EE_DATA_ADDR) / REC_SIZE);

const uint8_t OUT_GRANT   = 1;
const uint8_t OUT_DENY    = 2;
const uint8_t OUT_NO_CARD = 3;

uint8_t journalHead = 0;      // next slot to write
bool journalWrapped = false;  // the ring has been round at least once

void journalReset() {
  EEPROM.put(EE_MAGIC_ADDR, EE_MAGIC);
  EEPROM.update(EE_HEAD_ADDR, 0);
  EEPROM.update(EE_FLAGS_ADDR, 0);
  journalHead = 0;
  journalWrapped = false;
}

void journalLoad() {
  uint16_t magic;
  EEPROM.get(EE_MAGIC_ADDR, magic);
  if (magic != EE_MAGIC) {              // a fresh chip reads 0xFFFF: initialise rather than
    journalReset();                     // trusting whatever noise is in there
    return;
  }
  journalHead = EEPROM.read(EE_HEAD_ADDR);
  journalWrapped = EEPROM.read(EE_FLAGS_ADDR) & 0x01;
  if (journalHead >= EE_CAPACITY) journalReset();   // corrupt index: start clean
}

uint8_t journalCount() {
  return journalWrapped ? EE_CAPACITY : journalHead;
}

void journalWrite(const byte *uid, byte uidLen, uint8_t outcome, unsigned long now) {
  uint16_t addr = EE_DATA_ADDR + (uint16_t)journalHead * REC_SIZE;
  for (uint8_t i = 0; i < 4; i++)
    EEPROM.update(addr + i, i < uidLen ? uid[i] : 0);   // update(), not write(): no needless
  unsigned long secs = now / 1000UL;                     // cycles on bytes that did not change
  EEPROM.put(addr + 4, secs);
  EEPROM.update(addr + 8, outcome);

  journalHead = (journalHead + 1) % EE_CAPACITY;
  EEPROM.update(EE_HEAD_ADDR, journalHead);
  if (journalHead == 0 && !journalWrapped) {
    // Oldest records start being overwritten from here. Reconciliation cares about the
    // CURRENT outage, so discarding the oldest is the right trade - but the dump has to say
    // it happened, or a full journal reads as a complete one.
    journalWrapped = true;
    EEPROM.update(EE_FLAGS_ADDR, 0x01);
    Serial.println(F("JOURNAL_WRAPPED,0,oldest records now being overwritten"));
  }
}

void journalDump() {
  // Plain CSV on the wire: readable by eye in a serial monitor and parsable by
  // server/tools/import_uno_log.py without either end needing a library.
  uint8_t n = journalCount();
  Serial.print(F("JOURNAL_BEGIN,")); Serial.print(n);
  Serial.print(F(",capacity=")); Serial.print(EE_CAPACITY);
  Serial.print(F(",wrapped=")); Serial.println(journalWrapped ? 1 : 0);
  Serial.println(F("uid,seconds_since_boot,outcome"));
  // Oldest first. Once wrapped, the oldest surviving record is the one at the write head.
  for (uint8_t k = 0; k < n; k++) {
    uint8_t slot = journalWrapped ? (uint8_t)((journalHead + k) % EE_CAPACITY) : k;
    uint16_t addr = EE_DATA_ADDR + (uint16_t)slot * REC_SIZE;
    for (uint8_t b = 0; b < 4; b++) {
      byte v = EEPROM.read(addr + b);
      if (v < 0x10) Serial.print('0');
      Serial.print(v, HEX);
      if (b < 3) Serial.print(' ');
    }
    unsigned long secs; EEPROM.get(addr + 4, secs);
    uint8_t outcome = EEPROM.read(addr + 8);
    Serial.print(','); Serial.print(secs); Serial.print(',');
    Serial.println(outcome == OUT_GRANT ? F("granted")
                 : outcome == OUT_DENY  ? F("denied") : F("approach_no_card"));
  }
  Serial.println(F("JOURNAL_END"));
}

void journalSerialCommands() {
  static char buf[8];
  static uint8_t n = 0;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      buf[n] = 0;
      if (n) {
        if (!strcmp(buf, "D")) journalDump();
        else if (!strcmp(buf, "?")) {
          Serial.print(F("JOURNAL_STATUS,")); Serial.print(journalCount());
          Serial.print('/'); Serial.print(EE_CAPACITY);
          Serial.print(F(",wrapped=")); Serial.println(journalWrapped ? 1 : 0);
        }
        // Spelled out rather than a single key: clearing a security journal by fat-fingering
        // one character in a serial monitor is not a mistake worth making possible.
        else if (!strcmp(buf, "CLEAR")) { journalReset(); Serial.println(F("JOURNAL_CLEARED,0,")); }
      }
      n = 0;
    } else if (n < sizeof(buf) - 1) {
      buf[n++] = c;
    }
  }
}

void onHeartbeat() {
  // An interrupt, not polling: loop() spends up to 25 ms inside pulseIn waiting for an echo,
  // and polling would drop edges during exactly the window when knowing the smart path is
  // alive matters most.
  lastBeatMs = millis();
  everBeat = true;
}

unsigned long beatAge() {
  // A four-byte read on an 8-bit AVR is not atomic: an interrupt landing mid-read yields a
  // garbage timestamp, which would fake a healthy system or a dead one at random.
  noInterrupts();
  unsigned long t = lastBeatMs;
  bool seen = everBeat;
  interrupts();
  if (!seen) return HB_TIMEOUT_MS + 1;   // never heard one: assume down, never assume health
  return millis() - t;
}

float readDistanceCm() {
  digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(3);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long us = pulseIn(PIN_ECHO, HIGH, 25000UL);
  return us ? us / 58.0f : -1.0f;
}

bool pollSonar() {                       // true on the rising edge of "someone is there"
  lastCm = readDistanceCm();
  bool nowBlocked = blocked
      ? !(lastCm <= 0 || lastCm > TRIP_CM + HYST_CM)
      : (lastCm > 0 && lastCm < TRIP_CM);
  if (nowBlocked == cand) { if (agree < AGREE_NEEDED) agree++; }
  else { cand = nowBlocked; agree = 1; }
  if (agree >= AGREE_NEEDED && cand != blocked) { blocked = cand; return blocked; }
  return false;
}

void uidToString(char *out, size_t n) {
  out[0] = 0;
  for (byte i = 0; i < rfid.uid.size && (i * 3 + 3) < n; i++) {
    if (i) strcat(out, " ");
    char b[4];
    snprintf(b, sizeof(b), "%02X", rfid.uid.uidByte[i]);
    strcat(out, b);
  }
}

const char *holderFor(const char *uid) {
  for (int i = 0; i < CHARON_CARD_COUNT; i++)
    if (strcasecmp(uid, CHARON_CARDS[i].uid) == 0) return CHARON_CARDS[i].holder;
  return nullptr;
}

void grant(const char *holder, unsigned long now) {
  Serial.print(F("PASS,")); Serial.print(now);
  Serial.print(F(",card accepted: ")); Serial.println(holder);
  journalWrite(rfid.uid.uidByte, rfid.uid.size, OUT_GRANT, now);
  passUntil = now + PASS_HOLD_MS;
  buzzUntil = now + BUZZ_MS;
  approachAt = 0;                        // identified: no unattended-approach record needed
}

void refuse(const char *uid, unsigned long now) {
  // The UID is printed on purpose: this is the enrolment path. Tap an unknown card, read its
  // number off the serial monitor, put it in cards.h.
  Serial.print(F("DENY,")); Serial.print(now);
  Serial.print(F(",card not on this board's list: ")); Serial.println(uid);
  journalWrite(rfid.uid.uidByte, rfid.uid.size, OUT_DENY, now);
  denyUntil = now + DENY_HOLD_MS;
  buzzUntil = now + BUZZ_MS;
  approachAt = 0;
}

void setup() {
  pinMode(PIN_HB, INPUT);        // the ESP drives this actively; no pull-up, or a disconnected
                                 // wire would be held at a steady level and look deliberate
  pinMode(PIN_TRIG, OUTPUT); pinMode(PIN_ECHO, INPUT); digitalWrite(PIN_TRIG, LOW);
  pinMode(PIN_BUZZ, OUTPUT);  digitalWrite(PIN_BUZZ, LOW);
  pinMode(PIN_GREEN, OUTPUT); digitalWrite(PIN_GREEN, LOW);
  pinMode(PIN_RED, OUTPUT);   digitalWrite(PIN_RED, LOW);

  attachInterrupt(digitalPinToInterrupt(PIN_HB), onHeartbeat, CHANGE);

  SPI.begin();
  rfid.PCD_Init();

  Serial.begin(9600);
  Serial.println(F("[uno] charon gate failover"));
  Serial.print(F("[uno] cards on this board: ")); Serial.println(CHARON_CARD_COUNT);
  if (CHARON_CARD_COUNT == 0)
    Serial.println(F("[uno] WARNING: no cards enrolled - failover will refuse everyone"));
  // Report the reader's own version: 0x00 or 0xFF means the wiring is wrong, and finding that
  // out at boot is far better than discovering it mid-take.
  byte v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  Serial.print(F("[uno] MFRC522 version 0x")); Serial.println(v, HEX);
  if (v == 0x00 || v == 0xFF)
    Serial.println(F("[uno] WARNING: reader not responding - check SPI wiring and 3.3V supply"));
  journalLoad();
  Serial.print(F("[uno] failover journal: ")); Serial.print(journalCount());
  Serial.print('/'); Serial.print(EE_CAPACITY);
  Serial.println(journalWrapped ? F(" records (wrapped)") : F(" records"));
  Serial.println(F("[uno] serial: D = dump journal, ? = status, CLEAR = erase"));
  Serial.println(F("[uno] state,millis,detail"));
}

void loop() {
  unsigned long now = millis();
  journalSerialCommands();
  bool up = beatAge() < HB_TIMEOUT_MS;

  if (up != smartPathUp || !announced) {
    smartPathUp = up; announced = true;
    if (up) {
      Serial.print(F("SMART_UP,"));   Serial.print(now);
      Serial.println(F(",heartbeat present - standing down"));
      digitalWrite(PIN_RED, LOW);
      approachAt = 0;
    } else {
      Serial.print(F("SMART_DOWN,")); Serial.print(now);
      Serial.println(F(",no heartbeat - this board now owns the gate"));
      // Re-arm the sonar so someone already standing there when the smart path dies still
      // produces a fresh edge instead of being missed as "already blocked".
      blocked = false; cand = false; agree = 0; approachAt = 0;
    }
  }

  // Red means armed while the smart path is down, and doubles as the refusal light. Driven
  // from one place so the two meanings cannot fight each other.
  digitalWrite(PIN_RED, (!smartPathUp || (long)(denyUntil - now) > 0) ? HIGH : LOW);

  if (now - lastPingMs >= SONAR_PERIOD_MS) {
    lastPingMs = now;
    bool arrived = pollSonar();
    if (arrived && !smartPathUp && (long)(passUntil - now) <= 0) {
      approachAt = now;                  // start waiting for a card
      Serial.print(F("APPROACH,")); Serial.print(now);
      Serial.print(F(",presence at ")); Serial.print(lastCm, 0);
      Serial.println(F("cm - waiting for a card"));
    }
  }

  // Somebody came to the gate during an outage and never identified themselves. Worth a line
  // in the log: this is the signal the presence-only version threw away by simply opening.
  if (approachAt && (long)(now - approachAt - APPROACH_WAIT_MS) >= 0) {
    Serial.print(F("NO_CARD,")); Serial.print(now);
    Serial.println(F(",approach with no card presented"));
    { byte none[4] = {0, 0, 0, 0}; journalWrite(none, 4, OUT_NO_CARD, now); }
    approachAt = 0;
  }

  // The reader only acts while the smart path is down. With the brain alive this board stays
  // quiet on purpose: two systems deciding one gate is worse than either alone.
  if (!smartPathUp && rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    char uid[32];
    uidToString(uid, sizeof(uid));
    bool repeat = (strcmp(uid, lastUid) == 0) && ((long)(now - lastUidAt) < (long)SAME_CARD_MS);
    strncpy(lastUid, uid, sizeof(lastUid) - 1);
    lastUidAt = now;
    if (!repeat) {
      const char *holder = holderFor(uid);
      if (holder) grant(holder, now); else refuse(uid, now);
    }
    rfid.PICC_HaltA();
  }

  // Green runs on its own hold rather than being cut the instant the brain returns: a person
  // mid-walk-through should not have the light yanked out from under them.
  digitalWrite(PIN_GREEN, (long)(passUntil - now) > 0 ? HIGH : LOW);
  digitalWrite(PIN_BUZZ,  (long)(buzzUntil - now) > 0 ? HIGH : LOW);
}
