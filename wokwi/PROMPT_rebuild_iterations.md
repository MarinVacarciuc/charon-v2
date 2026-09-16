# Prompt: rebuild the Unit 21 Arduino alarm iteration set

Copy everything below the line into a fresh AI session (any capable assistant with the ability to
browse to wokwi.com and drive a browser, or with a human relaying its instructions). It is
self-contained - the assistant does not need access to this project, Moodle, or any prior
conversation.

---

## Context

This is coursework for a BTEC HND unit called *Emerging Technologies*. The assignment scenario is a
fictional company, **Ezra and Korede Security Ltd**, which wants a smart security/alarm system. The
brief requires a working prototype built on an **Arduino Uno with an ultrasonic (HC-SR04) sensor**,
and it specifically requires evidence of **multiple iterations**, each one an improvement made in
response to a limitation found in the version before it - a single finished circuit is not enough on
its own.

**Context on where this fits in the real project:** the Arduino line (Systems One through Four) is
not the whole project and is not presented as a finished answer - it is the first four iterations of
one continuous access-control system. In the real project, System Four's own stated limitation (a
shared PIN cannot identify a specific person) is what caused the Uno to be abandoned entirely in
favour of an ESP32 board with a camera and face recognition, because that limitation has no fix on
an 8-bit microcontroller. If this prompt is being used to produce evidence for that same
assignment, present Systems One-Four exactly as what they are: the required starting hardware (P5)
and its early iterations, not a separate or competing system next to whatever runs on better
hardware.

Three specific circuits already exist as the official starting material for this unit (given to
every student). They are reproduced exactly below. The task is to:

1. **Rebuild all three exactly as given** (Systems One, Two, Three) as three separate Wokwi
   projects, matching the code and the wiring precisely - these are not to be improved or corrected,
   only reproduced faithfully, because their value as evidence depends on being verifiably identical
   to the official material.
2. **Design and build a fourth system** that is a genuine, well-reasoned improvement over System
   Three, with new features chosen because they answer a specific limitation of the first three
   designs and because they map onto what the assignment brief actually rewards (detailed below,
   section "What System Four should add and why") - not just "more LEDs" or arbitrary extra
   hardware.
3. **Save all four as public Wokwi projects** and report back the four URLs.

Do not spend time running or testing the simulations in the Wokwi browser preview - the live
simulator can be slow/rate-limited on the free tier. Paste the code and wiring, save the project as
Public, and move on. Getting the sketch and diagram text exactly right matters far more than
watching it run.

---

## System One - presence and an audible alarm

A single distance threshold triggers a buzzer whose ON-time is proportional to how close the object
is.

**Wiring:** Arduino Uno + one HC-SR04 ultrasonic sensor + one piezo buzzer.
- HC-SR04: VCC → 5V, GND → GND, TRIG → pin 6, ECHO → pin 5
- Buzzer: one leg → pin 2, the other → GND

**sketch.ino** (reproduce exactly, including the original variable names and spacing):

```cpp
#define trigPin 6
#define echoPin 5
#define buzzer 2

float new_delay;

void setup()
{
  Serial.begin (9600);
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(buzzer,OUTPUT);
}

void loop()
{
  long duration, distance;
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  duration = pulseIn(echoPin, HIGH);
  distance = (duration/2) / 29.1;
  new_delay= (distance *3) +30;
  Serial.print(distance);
  Serial.println("  cm");
  if (distance < 50)
  {
    digitalWrite(buzzer,HIGH);
    delay(new_delay);
    digitalWrite(buzzer,LOW);
  }
  else
  {
    digitalWrite(buzzer,LOW);
  }
  delay(200);
}
```

---

## System Two - a graduated response

Six LEDs (two green, two yellow, two red) plus a buzzer whose pitch rises as an object gets closer,
across six distance bands.

**Wiring:** Arduino Uno + one HC-SR04 + six LEDs each with its own ~220 ohm resistor + one buzzer.
- HC-SR04: TRIG → pin 7, ECHO → pin 6, VCC → 5V, GND → GND
- LEDs (anode through resistor to the pin, cathode to GND): green → pin 13, green → pin 12,
  yellow → pin 11, yellow → pin 10, red → pin 9, red → pin 8
- Buzzer: one leg → pin 3, the other → GND

**sketch.ino** (reproduce exactly):

```cpp
#define trigPin 7
#define echoPin 6
#define led 13
#define led2 12
#define led3 11
#define led4 10
#define led5 9
#define led6 8
#define buzzer 3
int sound = 250;
void setup() {
  Serial.begin (9600);
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(led, OUTPUT);
  pinMode(led2, OUTPUT);
  pinMode(led3, OUTPUT);
  pinMode(led4, OUTPUT);
  pinMode(led5, OUTPUT);
  pinMode(led6, OUTPUT);
  pinMode(buzzer, OUTPUT);
}
void loop() {
  long duration, distance;
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  duration = pulseIn(echoPin, HIGH);
  distance = (duration/2) / 29.1;
  if (distance <= 30) {
    digitalWrite(led, HIGH);
    sound = 250;
  }
  else {
    digitalWrite(led,LOW);
  }
  if (distance < 25) {
    digitalWrite(led2, HIGH);
    sound = 260;
  }
  else {
    digitalWrite(led2, LOW);
  }
  if (distance < 20) {
    digitalWrite(led3, HIGH);
    sound = 270;
  }
  else {
    digitalWrite(led3, LOW);
  }
  if (distance < 15) {
    digitalWrite(led4, HIGH);
    sound = 280;
  }
  else {
    digitalWrite(led4,LOW);
  }
  if (distance < 10) {
    digitalWrite(led5, HIGH);
    sound = 290;
  }
  else {
    digitalWrite(led5,LOW);
  }
  if (distance < 5) {
    digitalWrite(led6, HIGH);
    sound = 300;
  }
  else {
    digitalWrite(led6,LOW);
  }
  if (distance > 30 || distance <= 0){
    Serial.println("Out of range");
    noTone(buzzer);
  }
  else {
    Serial.print(distance);
    Serial.println(" cm");
    tone(buzzer, sound);
  }
  delay(500);
}
```

---

## System Three - a labelled risk display

A 16x2 LCD prints one of five named risk levels (Extreme/High/Medium/Low/Safe), each with its own
LED count and buzzer rhythm.

**Wiring:** Arduino Uno + one HC-SR04 + a 16x2 parallel LCD (not I2C - six data/control lines) +
four red LEDs + one green LED + one buzzer.
- HC-SR04: TRIG → pin 8, ECHO → pin 7, VCC → 5V, GND → GND
- LCD (`LiquidCrystal lcd(11, 10, 5, 4, 3, 2)`): RS → 11, E → 10, D4 → 5, D5 → 4, D6 → 3, D7 → 2,
  VSS → GND, VDD → 5V, V0 → GND (full contrast), RW → GND, A (backlight anode) → 5V,
  K (backlight cathode) → GND
- Red LEDs, each through a resistor to GND: pins 6, 9, 12, 13
- Green "no risk" LED through a resistor to GND: pin A2
- Buzzer: one leg → pin A0, the other → GND

**sketch.ino** (reproduce exactly, including the inconsistent spacing - it is copied verbatim from
the original, which was built in Tinkercad):

```cpp
#include<LiquidCrystal.h>
int  trig = 8;
int echo = 7;
long duration;
int distance;
int ledPin1=6;
int  ledPin2=9;
int ledPin3=12;
int ledPin4=13;
int norisk=A2;
int buzz=A0;
LiquidCrystal  lcd(11, 10, 5, 4, 3, 2);
void setup()
{
pinMode(trig, OUTPUT);
pinMode(echo,  INPUT);
lcd.begin(16, 2);
Serial.begin(9600);
pinMode(ledPin1,OUTPUT);
pinMode(ledPin2,OUTPUT);
pinMode(ledPin3,OUTPUT);
pinMode(ledPin4,OUTPUT);
pinMode(norisk,OUTPUT);
pinMode(buzz,OUTPUT);
lcd.begin(16,2);
lcd.print("Starting  System");
delay(1500);
lcd.clear();
lcd.print("System On");
delay(4000);
}
void loop()
{
digitalWrite(trig,  LOW);
delayMicroseconds(5);
digitalWrite(trig, HIGH);
delayMicroseconds(10);
digitalWrite(trig, LOW);
duration = pulseIn(echo, HIGH);
distance  = duration*0.034/2;
Serial.print("Distance:");
Serial.println(distance);
if (distance <= 25){
lcd.setCursor(0,0);
lcd.print("Extreme  Risk");
lcd.setCursor(0,11);
lcd.print("Glowing 4 LED");
digitalWrite(ledPin1, HIGH);
digitalWrite(ledPin2, HIGH);
digitalWrite(ledPin3,  HIGH);
digitalWrite(ledPin4, HIGH);
digitalWrite(norisk, LOW);
tone(buzz,900);
delay(100);
noTone(buzz);
delay(100);
}
else if (distance >= 26 && distance <=100){
lcd.setCursor(0,0);
lcd.print("High  Risk");
lcd.setCursor(0,11);
lcd.print("Glowing 3 LED");
digitalWrite(ledPin1, HIGH);
digitalWrite(ledPin2, HIGH);
digitalWrite(ledPin3,  HIGH);
digitalWrite(ledPin4, LOW);
digitalWrite(norisk, LOW);
tone(buzz,900);
delay(700);
noTone(buzz);
delay(700);
}
else if (distance >= 101 && distance <=150){
lcd.setCursor(0,0);
lcd.print("Medium  Risk");
lcd.setCursor(0,11);
lcd.print("Glowing 2 LED");
digitalWrite(ledPin1, HIGH);
digitalWrite(ledPin2, HIGH);
digitalWrite(ledPin3, LOW);
digitalWrite(ledPin4, LOW);
digitalWrite(norisk,  LOW);
tone(buzz,1200);
delay(100);
noTone(buzz);
delay(1200);
}
else if (distance >= 151 && distance <=250){
lcd.setCursor(0,0);
lcd.print("Low Risk");
lcd.setCursor(0,11);
lcd.print("Glowing  1 LED");
digitalWrite(ledPin1, HIGH);
digitalWrite(ledPin2,  LOW);
digitalWrite(ledPin3, LOW);
digitalWrite(ledPin4, LOW);
digitalWrite(norisk, LOW);
tone(buzz,900);
delay(300);
noTone(buzz);
delay(2000);
}
else{
lcd.setCursor(0,0);
lcd.print("Safe  No Risk");
lcd.setCursor(0,11);
lcd.print("Glowing Safe LED");
digitalWrite(ledPin1, LOW);
digitalWrite(ledPin2, LOW);
digitalWrite(ledPin3,  LOW);
digitalWrite(ledPin4, LOW);
digitalWrite(norisk, HIGH);
noTone(buzz);
}
}
```

---

## What System Four should add, and why

System Four is where independent design work actually happens, so it is specified as a problem to
solve rather than a parts list to copy. The three systems above share one structural weakness:
**they alarm on presence, not on identity.** A guard on their round, a cleaner at 6 a.m. and an
actual intruder all trip the same "Extreme Risk" state, because none of the three systems has any
way to tell them apart. That is the limitation System Four exists to answer, and every feature
choice should trace back to it or to another limitation named explicitly below - resist adding
hardware just because it is available.

The assignment's grading criteria specifically reward:
- **evidence of multiple iterations, each driven by a stated limitation of the version before it**
  (do not present System Four's features as a wish list; present each one as the answer to a named
  problem with System Three, the way Systems Two and Three are each explained above)
- **evaluating the solution's impact on the end-user's current working practices**, not just
  describing what the hardware does
- **considering ethical, social, economic and legal factors** in what the system does with data

Concretely, System Four should:

1. **Add a credential check**, so a legitimate entry is not treated as a threat at all. A 4x4
   keypad PIN is the simplest option that stays within Arduino Uno + breadboard parts (a card
   reader or biometric sensor is out of scope for this unit - that is what a face-recognition or
   RFID system on a more capable board would be for, and is worth one sentence acknowledging as a
   "beyond this prototype" limitation rather than something to attempt here).
2. **Show its own state, not just an alarm state.** None of Systems One-Three distinguish "armed and
   working" from "unpowered" - both look identical from a distance (nothing happening). Add a clear
   idle/armed indicator (an LCD message or a steady LED) so the system communicates that it is alive
   even when nobody has approached it.
3. **Handle the failure case a shared credential creates.** What happens after several wrong
   attempts matters for two competing reasons that should both be visible in the design: locking the
   system protects against someone guessing the code by brute force (fail-secure), but a lockout
   also denies a legitimate user who mistyped their own code (a real cost, not a free win). Whatever
   is chosen (a timed lockout, a limited retry count, an audible warning before locking), say
   explicitly which failure mode was prioritised and why, rather than presenting the lockout as pure
   upside.
4. **Consider what the system does NOT store.** A shared PIN is not personal data in the way a face
   or fingerprint would be, so this design avoids the data-protection burden a biometric system would
   carry (no special-category data, no DPIA). State this as a deliberate property of the design, not
   an accident - it is a genuine, defensible reason to prefer a PIN-based Uno system for a first
   iteration over jumping straight to biometrics.
5. **Keep it buildable on the same parts family as Systems One-Three** (Arduino Uno, HC-SR04, an
   LCD, a keypad, LEDs, a buzzer - all standard Wokwi library parts) so the four systems read as one
   continuous progression rather than a discontinuity.

Do not add IoT/network connectivity (Wi-Fi, MQTT, a web dashboard) to System Four unless
specifically asked - that is a separate, larger piece of coursework and conflating it with this
Arduino iteration set will make the iteration story harder to follow, not stronger.

Write a short design note (4-6 sentences) explaining System Four's features against the numbered
limitations above before building it, the same way each of Systems Two and Three above is explained
as an answer to a specific limitation in the version before it.

---

## How to build and save each one on Wokwi

For each of the four systems:

1. Open a new browser tab at **https://wokwi.com/projects/new/arduino-uno**
2. Click into the `sketch.ino` editor, select all (Ctrl/Cmd+A), and paste the code for that system
   over the default template.
3. Click the `diagram.json` tab, select all, and paste the wiring definition for that system (build
   this as a normal Wokwi diagram.json: a `wokwi-arduino-uno` part plus the sensor/LED/buzzer/LCD
   parts described above, wired according to the pin list given for that system - each LED needs
   its own `wokwi-resistor` in series, and the LCD needs the 6-wire parallel connections listed under
   System Three).
4. **Note on the live preview:** Wokwi's simulation panel sometimes does not repaint immediately
   after a paste, and can show a blank canvas even when the diagram is valid. Do not treat a blank
   preview as proof the diagram is broken - switching to the `sketch.ino` tab and back, or simply
   saving the project, is usually enough to make it render. Do not spend time debugging this; it is
   a rendering quirk, not a sign the JSON needs fixing.
5. Click **Save**, choose **Public**, and give the project a clear name, e.g.
   "Ezra and Korede - System One (Basic Buzzer Alarm)", "... System Four (Keypad Access Control)".
6. Record the resulting project URL (it appears in the browser address bar once saved).

Report back all four URLs at the end, labelled by system number, plus the short design note for
System Four.
