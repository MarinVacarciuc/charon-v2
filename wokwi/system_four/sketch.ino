/*
  Ezra and Korede Security Ltd - Arduino iteration set, System Four

  Answers the limitation System Three exposed: Systems One through Three all alarm on
  PRESENCE, so a guard on their round, a cleaner at 6am and an actual intruder all trip the
  same "Extreme Risk" state. There is no way for the system to tell them apart. This version
  adds a credential check, so a legitimate entry is not treated as a threat at all.

  CORRECTION (2026-09-20): an earlier build of this iteration used a 4x4 membrane keypad and
  a shared 4-digit PIN. It has been rebuilt on an RFID card reader (MFRC522) instead, kept on
  this same Uno + HC-SR04 + LCD parts family. The reasoning below is updated to match; the
  keypad build is preserved separately as evidence for a different end user (see the
  project's own README/ITERATIONS.md) rather than edited in place, because a design that was
  actually built and tested should not quietly become something else in the record.

  Three further limitations are addressed deliberately, not by accident:

  1. None of Systems One-Three distinguish "armed and watching" from "unpowered" - both look
     like nothing happening. This version keeps a visible idle state (LCD message + steady
     green LED) so the system communicates it is alive even when nobody has approached it.

  2. A failed-credential failure mode has two competing costs: locking the reader after
     repeated unrecognised cards protects against someone working through a stack of blank or
     stolen cards (fail-secure), but a lockout also denies a legitimate staff member whose own
     card is simply not read cleanly on the first tap. The choice made here mirrors the
     keypad build's own compromise: three unsuccessful presentations in a row trigger a short,
     clearly-communicated lockout (30 seconds, red LED, audible tone) rather than locking on
     the very first misread. This prioritises not punishing a fumbled tap over maximising
     resistance to a determined attacker, which is a defensible choice for a staff entrance
     rather than a bank vault.

  3. An RFID card's UID is not biometric data - it is not derived from anyone's body, and UK
     GDPR's Article 9 special-category rules that apply to a face or fingerprint do not apply
     to it. This design also does not build any per-card identity log: the reader checks UID
     membership in a short whitelist and reports grant/deny, nothing more - it does not record
     WHICH authorised card was used or attach a name to an entry. Operationally that keeps it
     equivalent to a shared PIN: valid or invalid, not who. Recording who used which card, and
     revoking one person's access without reissuing everyone else's, needs persistent storage
     and a reporting channel this bare Uno does not have - which is exactly the gap the
     project's later, server-backed iterations exist to fill (see the project report).

  Wiring: Arduino Uno, HC-SR04 (TRIG D2, ECHO D3), MFRC522 RFID reader (SDA D10, SCK D13,
  MOSI D11, MISO D12, RST D9, VCC 3.3V, GND GND), 16x2 I2C LCD (SDA A4, SCL A5), a green
  "armed" LED (D5) and a red "alarm/lockout" LED (D6) each through a ~220R resistor, and a
  buzzer (D4). See diagram.json for the exact wiring definition.
*/
#include <SPI.h>
#include <MFRC522.h>
#include <LiquidCrystal_I2C.h>

#define trigPin 2
#define echoPin 3
#define buzzer 4
#define armedLed 5
#define alarmLed 6
#define SS_PIN 10
#define RST_PIN 9

MFRC522 rfid(SS_PIN, RST_PIN);
LiquidCrystal_I2C lcd(0x27, 16, 2);

const int entryZone = 80;
const int maxAttempts = 3;
const unsigned long lockoutTime = 30000;
const unsigned long cardWaitTime = 8000;

// Whitelisted card UIDs (employee badges) - Blue Card and Green Card presets in the Wokwi
// simulator's own MFRC522 model. On real hardware, replace these with the UIDs printed on
// the serial monitor the first time each real card is tapped.
byte authorizedUID[][4] = {
  {0x01, 0x02, 0x03, 0x04},
  {0x11, 0x22, 0x33, 0x44}
};
const int numAuthorized = 2;

int failedAttempts = 0;
bool armedDisplayed = false;

long readDistanceCm() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  long duration = pulseIn(echoPin, HIGH);
  return (duration / 2) / 29.1;
}

void showArmed() {
  digitalWrite(armedLed, HIGH);
  digitalWrite(alarmLed, LOW);
  noTone(buzzer);
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("System Armed");
  lcd.setCursor(0, 1);
  lcd.print("Ready...");
}

void triggerLockout() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("LOCKED OUT");
  lcd.setCursor(0, 1);
  lcd.print("Wait 30s...");
  digitalWrite(armedLed, LOW);
  unsigned long start = millis();
  while (millis() - start < lockoutTime) {
    digitalWrite(alarmLed, HIGH);
    tone(buzzer, 1000);
    delay(150);
    digitalWrite(alarmLed, LOW);
    noTone(buzzer);
    delay(150);
  }
  failedAttempts = 0;
}

bool isAuthorized() {
  for (int i = 0; i < numAuthorized; i++) {
    bool match = true;
    for (byte j = 0; j < 4; j++) {
      if (rfid.uid.uidByte[j] != authorizedUID[i][j]) {
        match = false;
        break;
      }
    }
    if (match) return true;
  }
  return false;
}

bool waitForCard() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Present Card");
  unsigned long start = millis();
  while (millis() - start < cardWaitTime) {
    if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
      return true;
    }
    delay(50);
  }
  return false;
}

void setup() {
  Serial.begin(9600);
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(buzzer, OUTPUT);
  pinMode(armedLed, OUTPUT);
  pinMode(alarmLed, OUTPUT);

  SPI.begin();
  rfid.PCD_Init();

  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Ezra & Korede");
  lcd.setCursor(0, 1);
  lcd.print("Security System");
  delay(2000);

  showArmed();
  armedDisplayed = true;
}

void loop() {
  long distance = readDistanceCm();
  Serial.print("Distance: ");
  Serial.println(distance);

  if (distance > 0 && distance <= entryZone) {
    armedDisplayed = false;
    tone(buzzer, 600, 150);

    bool presented = waitForCard();

    if (presented && isAuthorized()) {
      failedAttempts = 0;
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("Access Granted");
      digitalWrite(armedLed, HIGH);
      tone(buzzer, 1500, 200);
      rfid.PICC_HaltA();
      delay(3000);
    } else {
      failedAttempts++;
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print(presented ? "Card Not Known" : "No Card Shown");
      lcd.setCursor(0, 1);
      lcd.print("Left: ");
      lcd.print(maxAttempts - failedAttempts);
      tone(buzzer, 400, 400);
      delay(1500);
      if (presented) rfid.PICC_HaltA();

      if (failedAttempts >= maxAttempts) {
        triggerLockout();
      }
    }
    showArmed();
    armedDisplayed = true;
  } else {
    if (!armedDisplayed) {
      showArmed();
      armedDisplayed = true;
    }
    delay(200);
  }
}
