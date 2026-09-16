/*
  CIRCUIT DIAGRAM FOR A BASIC SECURITY SYSTEM WITH AN ULTRASONIC SENSOR AND ARDUINO
  Five-tier risk display with LCD feedback - 1 METRE BENCH VARIANT

  This is NOT the file to use for the report or the Wokwi evidence - that is sketch.ino in
  this same folder, kept byte-for-byte identical to the Moodle original per ITERATIONS.md.
  This variant only exists because the bench space available for live hardware testing did
  not have room for the original 250 cm range. The four risk tiers are scaled down to fit a
  1 metre working distance, keeping the same 4-tier proportions as the original rather than
  picking arbitrary numbers:

    Original (max 250 cm)          This variant (max 100 cm)
    Extreme  0-25    (25 cm span)  Extreme  0-10    (10 cm span)
    High     26-100  (75 cm span)  High     11-40   (30 cm span)
    Medium   101-150 (50 cm span)  Medium   41-70   (30 cm span)
    Low      151-250 (100 cm span) Low      71-100  (30 cm span)
    Safe     >250                 Safe     >100

  Everything else (LED count per tier, buzzer pattern per tier, LCD text) is unchanged.
*/
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
//pinMode(A5, INPUT);
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
if (distance <= 10){
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
else if (distance >= 11 && distance <=40){
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
else if (distance >= 41 && distance <=70){
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
else if (distance >= 71 && distance <=100){
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
