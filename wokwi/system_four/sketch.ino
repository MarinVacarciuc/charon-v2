/*
  Ezra and Korede Security Ltd - Arduino iteration set, System Four

  Answers the limitation System Three exposed: Systems One through Three all alarm on
  PRESENCE, so a guard on their round, a cleaner at 6am and an actual intruder all trip the
  same "Extreme Risk" state. There is no way for the system to tell them apart. This version
  adds a credential check, so a legitimate entry is not treated as a threat at all.

  Three further limitations of a naive keypad add-on are addressed deliberately, not by
  accident:

  1. None of Systems One-Three distinguish "armed and watching" from "unpowered" - both look
     like nothing happening. This version keeps a visible idle state (LCD message + steady
     green LED) so the system communicates it is alive even when nobody has approached it.

  2. A wrong-code failure mode has two competing costs: locking the system protects against
     someone guessing the code by brute force (fail-secure), but a lockout also denies a
     legitimate user who mistyped their own code. The choice made here is a warn-then-lock
     compromise: attempt 2 gets an audible "last try" warning rather than a silent countdown
     to failure, and only attempt 3 triggers a short, clearly-communicated lockout. This
     prioritises not punishing a fumbled PIN over maximising resistance to a determined
     attacker, which is a defensible choice for a staff entrance rather than a bank vault.

  3. A PIN is a shared secret, not biometric data. This system stores nothing that UK GDPR
     treats as special category data, so it carries no DPIA obligation and no retention
     policy the way a face or fingerprint credential would. That is a deliberate property of
     staying on an Arduino Uno for this iteration, not an oversight - see the project report
     for where individual-identity credentials (which DO require that governance) are picked
     up instead.

  Known limitation carried forward, not fixed here: the code is shared by the whole team, so
  the system can prove a valid code was entered and never who entered it. Individual
  credentials are out of scope for an Arduino Uno + breadboard build.
*/
#include <Keypad.h>
#include <LiquidCrystal_I2C.h>

#define trigPin 9
#define echoPin 8
#define buzzer 10
#define redLed 13
#define greenLed 12

const byte ROWS = 4;
const byte COLS = 4;
char keys[ROWS][COLS] = {
  {'1', '2', '3', 'A'},
  {'4', '5', '6', 'B'},
  {'7', '8', '9', 'C'},
  {'*', '0', '#', 'D'}
};
byte rowPins[ROWS] = {5, 4, 3, 2};
byte colPins[COLS] = {7, 6, A1, A0};
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

LiquidCrystal_I2C lcd(0x27, 16, 2);

const String accessCode = "4321";
const int triggerDistance = 30;    // cm - matches the approach range used in Systems One-Three
const byte maxAttempts = 3;
const unsigned long lockoutDuration = 20000UL;   // 20s: short enough to demo, long enough to matter

enum State { SYS_IDLE, CODE_ENTRY, GRANTED, LOCKED_OUT };
State state = SYS_IDLE;

String enteredCode = "";
byte wrongAttempts = 0;
unsigned long lockoutUntil = 0;
unsigned long stateChangedAt = 0;

void setup()
{
  Serial.begin(9600);
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(buzzer, OUTPUT);
  pinMode(redLed, OUTPUT);
  pinMode(greenLed, OUTPUT);

  lcd.init();
  lcd.backlight();
  showIdle();
  Serial.println("System Four armed");
}

void loop()
{
  long distance = readDistance();

  switch (state)
  {
    case SYS_IDLE:
      if (distance > 0 && distance < triggerDistance)
      {
        state = CODE_ENTRY;
        enteredCode = "";
        showEnterCode();
      }
      break;

    case CODE_ENTRY:
      if (distance <= 0 || distance >= triggerDistance)
      {
        // Walked away mid-entry: no penalty, just reset. A missed sensor reading (distance
        // <= 0) must not be treated the same as a real threshold crossing.
        state = SYS_IDLE;
        showIdle();
      }
      else
      {
        readKeypad();
      }
      break;

    case GRANTED:
      if (millis() - stateChangedAt > 3000)
      {
        state = SYS_IDLE;
        showIdle();
      }
      break;

    case LOCKED_OUT:
      updateLockoutScreen();
      if (millis() >= lockoutUntil)
      {
        wrongAttempts = 0;
        state = SYS_IDLE;
        showIdle();
      }
      break;
  }

  delay(150);
}

void readKeypad()
{
  char key = keypad.getKey();
  if (!key) return;

  if (key == '*')
  {
    enteredCode = "";
    showEnterCode();
    return;
  }

  if (key == '#')
  {
    if (enteredCode == accessCode)
    {
      wrongAttempts = 0;
      state = GRANTED;
      stateChangedAt = millis();
      digitalWrite(greenLed, HIGH);
      digitalWrite(redLed, LOW);
      lcd.clear();
      lcd.print("Access Granted");
      lcd.setCursor(0, 1);
      lcd.print("Welcome");
      Serial.println("GRANTED");
    }
    else
    {
      wrongAttempts++;
      enteredCode = "";
      if (wrongAttempts >= maxAttempts)
      {
        state = LOCKED_OUT;
        lockoutUntil = millis() + lockoutDuration;
        digitalWrite(greenLed, LOW);
        digitalWrite(redLed, HIGH);
        tone(buzzer, 300);
        delay(600);
        noTone(buzzer);
        Serial.println("LOCKED OUT");
      }
      else if (wrongAttempts == maxAttempts - 1)
      {
        // The warning the design note above commits to: one audible "last try" cue before
        // the lockout actually fires, rather than a silent countdown to failure.
        lcd.clear();
        lcd.print("Wrong code");
        lcd.setCursor(0, 1);
        lcd.print("Last attempt!");
        tone(buzzer, 500, 150);
        delay(400);
        tone(buzzer, 500, 150);
        delay(1200);
        showEnterCode();
      }
      else
      {
        lcd.clear();
        lcd.print("Wrong code");
        tone(buzzer, 400, 200);
        delay(800);
        showEnterCode();
      }
    }
    return;
  }

  if (enteredCode.length() < 8)
  {
    enteredCode += key;
    lcd.setCursor(0, 1);
    for (byte i = 0; i < enteredCode.length(); i++) lcd.print('*');
  }
}

void showIdle()
{
  lcd.clear();
  lcd.print("System Armed");
  lcd.setCursor(0, 1);
  lcd.print("Approach to enter");
  digitalWrite(greenLed, HIGH);
  digitalWrite(redLed, LOW);
  noTone(buzzer);
}

void showEnterCode()
{
  lcd.clear();
  lcd.print("Enter code:");
  digitalWrite(greenLed, LOW);
}

void updateLockoutScreen()
{
  unsigned long remaining = (lockoutUntil > millis()) ? (lockoutUntil - millis()) : 0;
  lcd.setCursor(0, 0);
  lcd.print("Locked out");
  lcd.setCursor(0, 1);
  lcd.print(remaining / 1000);
  lcd.print("s remaining   ");
}

long readDistance()
{
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  long duration = pulseIn(echoPin, HIGH, 25000);
  if (duration == 0) return -1;
  return (duration / 2) / 29.1;
}
