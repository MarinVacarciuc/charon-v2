/*
  CIRCUIT DIAGRAM FOR A BASIC SECURITY SYSTEM WITH AN ULTRASONIC SENSOR AND ARDUINO
  Security Alarm with Ultrasonic Sensor

  Source: Moodle-provided reference design, Unit 21 practical (Alarm System One).
  Reproduced verbatim, including the original variable names and formatting, so
  this project is the same starting point the module gave every student, not a
  cleaned-up rewrite of it.
*/
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
