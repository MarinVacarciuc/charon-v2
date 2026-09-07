# Uno failover - wiring

Read this beside the board. Everything here is checkable: after each section there is a way
to prove it worked before moving on, so a mistake is found where it was made rather than three
steps later.

## Before you start

Both boards must run from the **same power bank**. Not because of power, but because they
need a **common ground** - see the very first warning below.

You need: the Uno, the MFRC522 reader + at least one card, a spare RCWL-1601, a buzzer, a
green and a red LED, two ~330R resistors, and jumper wire.

---

## 1. The one that will actually bite you: ground and direction

**Common ground.** Run a wire from any **GND** on the ESP32 to any **GND** on the Uno.

Do this first, and do not skip it. Without a shared ground the heartbeat input has no
reference and floats, and a floating input reads as a **fast random square wave** - which is
indistinguishable from a healthy heartbeat. The board would sit there believing the smart
system is alive while it is dead. That is the worst failure this design can have, and it looks
like everything is fine.

**One direction only.** The heartbeat goes **ESP32 -> Uno** and never back. The ESP32 runs at
3.3 V and its pins are *not* 5 V tolerant: putting the Uno's 5 V onto an ESP32 GPIO destroys
it. The Uno reading 3.3 V as a logic high is fine, which is why this direction works and the
other does not.

---

## 2. Heartbeat

| From (gate-in ESP32-S3) | To (Uno) |
|---|---|
| GPIO 21 | D2 |
| GND | GND |

D2 must be D2 or D3 - they are the only external-interrupt pins on an Uno, and this signal is
read on an interrupt so it cannot be missed while the board is busy listening for an ultrasonic
echo.

**Check it:** power both, open the serial monitor at 9600. You should see `SMART_UP` within a
few seconds. Pull the GPIO 21 wire off; within about 3 seconds you get `SMART_DOWN`. Put it
back; `SMART_UP` returns. If it says `SMART_UP` with the wire *disconnected*, your ground is
missing - go back to section 1.

---

## 3. RFID reader (MFRC522)

**Its VCC goes to 3.3 V, not 5 V.** The reader's logic pins tolerate the Uno's 5 V signalling,
its supply does not. 5 V on VCC kills the module.

| MFRC522 | Uno |
|---|---|
| SDA (SS) | D10 |
| SCK | D13 |
| MOSI | D11 |
| MISO | D12 |
| RST | D3 |
| GND | GND |
| **VCC** | **3.3 V** |
| IRQ | not connected |

**Check it:** on boot the serial monitor prints `MFRC522 version 0x...`. Anything other than
`0x00` or `0xFF` means the reader is talking (`0x91` or `0x92` are the usual answers). If you
get `0x00` or `0xFF`, the sketch warns you explicitly - re-check SPI wiring and that VCC is on
3.3 V.

---

## 4. Ultrasonic, LEDs, buzzer

| Part | Uno |
|---|---|
| RCWL-1601 TRIG | D5 |
| RCWL-1601 ECHO | D6 |
| RCWL-1601 VCC | 3.3 V |
| RCWL-1601 GND | GND |
| Buzzer + | D7 |
| Green LED + (through ~330R) | D8 |
| Red LED + (through ~330R) | D9 |
| LED and buzzer - | GND |

The RCWL-1601 runs at 3.3 V deliberately: at that supply its echo output is 3.3 V logic, which
is why no level shifter is needed anywhere in this project. An HC-SR04 at 5 V would need one.

LEDs are polarised - the long leg is +. If one does not light, turn it around before assuming
anything is broken.

---

## 5. Enrol your cards

Card UIDs are not known in advance, so you read them off the board:

1. Flash the sketch, open the serial monitor at 9600.
2. Pull the heartbeat wire so the board goes into failover (`SMART_DOWN`). The reader is
   deliberately inert while the smart system is alive.
3. Tap a card. You get `DENY,...,card not on this board's list: 04 A3 19 2B`.
4. Copy that UID into `cards.h`:
   ```c
   static const CharonCard CHARON_CARDS[] = {
     {"04 A3 19 2B", "Marin"},
   };
   ```
5. Re-flash. Tap again: `PASS,...,card accepted: Marin`, green light, short chirp.

`cards.h` is gitignored on purpose. A card UID is a credential: anyone who knows one can write
it to a blank card.

---

## 6. Full check, in order

Power both boards from the bank, serial monitor open at 9600.

1. `SMART_UP` appears. Tap a card - **nothing happens**. Correct: the failover stays out of
   the way while the real system is running.
2. Pull the heartbeat wire. Within ~3 s: `SMART_DOWN`, red LED on.
3. Walk up to the ultrasonic. `APPROACH,...,waiting for a card`. Nothing opens.
4. Wait ~8 s without tapping. `NO_CARD,...,approach with no card presented`.
5. Tap a known card. `PASS`, green LED, chirp.
6. Tap an unknown card. `DENY`, red, and the UID printed.
7. Reconnect the heartbeat. `SMART_UP` within ~3 s, red goes out.

If all seven behave, Layer 3 is done and the last beat of the video is filmable.

## Flashing

```bash
cd ~/IdeaProjects/charon-v2/firmware
arduino-cli compile --fqbn arduino:avr:uno uno_watchdog
arduino-cli upload -p /dev/cu.usbmodemXXXX --fqbn arduino:avr:uno uno_watchdog
```

Find the port with `ls /dev/cu.usbmodem*` while the Uno is the only board plugged in.
