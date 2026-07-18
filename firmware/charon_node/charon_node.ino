/*
  Charon node - firmware v1 (gate / zone camera).

  Serves one JPEG at  http://<node>/shot.jpg  and announces itself as <NODE_ID>.local.
  That URL is exactly what the brain (prototype/process_server.py) already polls, so a node
  drops into CAM["url"] with no server-side change, and mDNS means a new hotspot IP does not
  have to be retyped.

  Camera routing is NOT the same across ESP32-S3 "CAM" boards - the FPC traces differ per
  vendor and a wrong map fails as "camera probe failed (0x105)". Rather than hard-code one,
  boot tries the known maps and keeps the first that initialises; the winner is printed on
  serial and shown at /, so it can be pinned once this batch is identified.
*/
#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiMulti.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include <Preferences.h>
#include <ArduinoOTA.h>
#include "secrets.h"

// Thresholds depend on the geometry of the spot each node ends up in, which is not known at flash
// time. Keep them settable over HTTP and persisted in NVS: six nodes on six walls must not each need
// a USB cable to be re-calibrated. The secrets.h values are only first-boot defaults.
Preferences prefs;

WiFiMulti wifiMulti;   // node roams between home / demo hotspot / college without a reflash

// RCWL-1601 ultrasonics, powered from 3V3 so their echo is 3.3V logic straight into a GPIO - no
// divider (an HC-SR04 at 5V would need one). Free pins here: the camera holds 4-18, octal PSRAM
// holds 33-37, flash 26-32, USB 19/20. (GPIO34-39 were input-only on the original ESP32; the S3 has
// no input-only pins, so 39 can drive a TRIG.)
//
// NEAR (39/38) means the same thing on every node: "someone is here". At the gate it is the approach
// sensor that wakes the camera; in a zone it is the presence sensor. PASS (41/40) exists only on the
// gate lanes and means a body actually crossed. An interior node simply has nothing wired to 41/40,
// reads no echo, and never reports a passage - no separate firmware needed.
struct Sonar {
  const char *name;
  uint8_t trig, echo;
  int thresh;          // cm; closer than this = something is there
  float cm;
  bool blocked;
  bool cand;
  uint8_t agree;
};
static Sonar S_NEAR = {"near", 39, 38, WAKE_DIST_CM, -1, false, false, 0};
static Sonar S_PASS = {"pass", 41, 40, PASS_DIST_CM, -1, false, false, 0};

// Access-decision LEDs. GPIO1/2 are free on every one of these boards (not camera, not octal
// PSRAM/flash, not USB, not a strapping pin) - unlike GPIO48/38, which some ESP32-S3 devkits wire to
// an onboard NeoPixel but this bare WROOM breakout does not have, so a real LED must be soldered here.
// The brain commands these over HTTP after it decides granted/denied; the node auto-clears whichever
// is lit after LED_HOLD_MS so a dropped "off" command (WiFi hiccup) cannot leave a colour stuck lit.
#define LED_GREEN_PIN 1
#define LED_RED_PIN   2
#define LED_HOLD_MS   3000
static uint32_t ledOffAt = 0;

static volatile uint32_t passages = 0;   // monotonic; the brain watches this increment

struct PinMap {
  const char *name;
  int8_t pwdn, reset, xclk, siod, sioc;
  int8_t y9, y8, y7, y6, y5, y4, y3, y2;
  int8_t vsync, href, pclk;
};

// Taken verbatim from the Arduino esp32 core camera_pins.h (v3.3.8). The S3-EYE routing is what
// most generic "ESP32-S3 WROOM CAM" boards clone, so it is tried first.
static const PinMap MAPS[] = {
  {"esp32s3-eye / freenove-s3-wroom", -1, -1, 15,  4,  5, 16, 17, 18, 12, 10,  8,  9, 11,  6,  7, 13},
  {"xiao-esp32s3-sense",              -1, -1, 10, 40, 39, 48, 11, 12, 14, 16, 18, 17, 15, 38, 47, 13},
  {"esp32s3-cam-lcd",                 -1, -1, 40, 17, 18, 39, 41, 42, 12,  3, 14, 47, 13, 21, 38, 11},
};
static const int N_MAPS = sizeof(MAPS) / sizeof(MAPS[0]);

WebServer server(80);
static const char *activeMap = "none";

static bool startCamera(const PinMap &m) {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer   = LEDC_TIMER_0;
  c.pin_pwdn     = m.pwdn;
  c.pin_reset    = m.reset;
  c.pin_xclk     = m.xclk;
  c.pin_sccb_sda = m.siod;
  c.pin_sccb_scl = m.sioc;
  c.pin_d7 = m.y9; c.pin_d6 = m.y8; c.pin_d5 = m.y7; c.pin_d4 = m.y6;
  c.pin_d3 = m.y5; c.pin_d2 = m.y4; c.pin_d1 = m.y3; c.pin_d0 = m.y2;
  c.pin_vsync = m.vsync;
  c.pin_href  = m.href;
  c.pin_pclk  = m.pclk;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size   = FRAMESIZE_VGA;                 // 640x480 - the Mac does the recognition, the node just feeds it
  c.jpeg_quality = 12;
  c.fb_count     = psramFound() ? 2 : 1;
  c.fb_location  = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  c.grab_mode    = CAMERA_GRAB_LATEST;            // hand the brain the newest frame, never a queued stale one
  return esp_camera_init(&c) == ESP_OK;
}

static float readDistanceCm(const Sonar &s) {
  digitalWrite(s.trig, LOW);  delayMicroseconds(3);
  digitalWrite(s.trig, HIGH); delayMicroseconds(10);
  digitalWrite(s.trig, LOW);
  unsigned long us = pulseIn(s.echo, HIGH, 25000UL);   // ~4 m ceiling; 0 = no echo came back
  return us ? us / 58.0f : -1.0f;
}

// Two ultrasonics on one board must never ping together or each hears the other's echo and reports
// a phantom wall. So exactly one fires per tick and they alternate.
//
// HYSTERESIS: a single trip distance is not enough. Clutter/multipath near the threshold (measured
// live on a cluttered desk: readings bouncing 17-65cm around a 60cm threshold) crosses one boundary
// back and forth on pure noise, counting a "passage" every time - 6 phantom counts in 8 seconds with
// nobody there. So the clearing distance is pushed HYST_CM further out than the tripping distance:
// once blocked, it stays blocked until the reading is unambiguously clear, so noise that never
// actually leaves the vicinity of the sensor cannot re-trigger a second phantom count.
// Two agreeing readings still debounce a single noisy sample before any transition is trusted.
#define HYST_CM 20
static bool pollSonar(Sonar &s) {
  s.cm = readDistanceCm(s);
  bool now_blocked = s.blocked
      ? !(s.cm <= 0 || s.cm > s.thresh + HYST_CM)   // stay blocked until clearly clear
      : (s.cm > 0 && s.cm < s.thresh);               // trip on clearly close
  if (now_blocked == s.cand) { if (s.agree < 2) s.agree++; }
  else { s.cand = now_blocked; s.agree = 1; }
  if (s.agree >= 2 && s.cand != s.blocked) {
    s.blocked = s.cand;
    return s.blocked;
  }
  return false;
}

static void handleShot() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { server.send(503, "text/plain", "no frame"); return; }
  // The brain already polls this several times a second, so the passage counter rides along in the
  // headers: no second request, and the node never needs to know the brain's (changing) address.
  server.sendHeader("X-Passage", String(passages));
  server.sendHeader("X-Dist-Cm", String(S_PASS.cm, 1));
  server.sendHeader("X-Near-Cm", String(S_NEAR.cm, 1));
  server.sendHeader("X-Near", S_NEAR.blocked ? "1" : "0");
  server.sendHeader("X-Node", NODE_ID);
  server.setContentLength(fb->len);
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "image/jpeg", "");
  server.sendContent((const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

static void handleLed() {
  String st = server.arg("state");
  digitalWrite(LED_GREEN_PIN, st == "green" ? HIGH : LOW);
  digitalWrite(LED_RED_PIN,   st == "red"   ? HIGH : LOW);
  ledOffAt = (st == "green" || st == "red") ? millis() + LED_HOLD_MS : 0;
  server.send(200, "text/plain", "led: " + st);
}

static void handlePassage() {                             // plain view for calibrating the threshold
  String s = String("{\"node\":\"") + NODE_ID + "\",\"passages\":" + passages +
             ",\"cm\":" + String(S_PASS.cm, 1) + ",\"blocked\":" + (S_PASS.blocked ? "true" : "false") +
             ",\"threshold_cm\":" + S_PASS.thresh +
             ",\"near_cm\":" + String(S_NEAR.cm, 1) + ",\"near\":" + (S_NEAR.blocked ? "true" : "false") +
             ",\"wake_cm\":" + S_NEAR.thresh + "}";
  server.send(200, "application/json", s);
}

// Calibrate in place: /threshold?cm=60 . Persisted, so it survives a reboot or a flat battery.
static void handleThreshold() {
  if (server.hasArg("cm")) {
    int v = server.arg("cm").toInt();
    if (v < 5 || v > 400) { server.send(400, "text/plain", "cm must be 5..400 (sensor range)"); return; }
    S_PASS.thresh = v;
    prefs.putInt("passcm", v);
  }
  if (server.hasArg("wake")) {
    int w = server.arg("wake").toInt();
    if (w < 5 || w > 400) { server.send(400, "text/plain", "wake must be 5..400 (sensor range)"); return; }
    S_NEAR.thresh = w;
    prefs.putInt("wakecm", w);
  }
  server.send(200, "application/json",
              String("{\"threshold_cm\":") + S_PASS.thresh + ",\"cm\":" + String(S_PASS.cm, 1) +
              ",\"wake_cm\":" + S_NEAR.thresh + ",\"near_cm\":" + String(S_NEAR.cm, 1) + "}");
}

static void handleRoot() {
  String s = String("charon node: ") + NODE_ID + "\n";
  // The boards are physically identical and the identity lives only in flash, so print the MAC:
  // it is the only way to tell which lump of hardware is answering to which name.
  s += String("mac        : ") + WiFi.macAddress() + "\n";
  s += String("camera map : ") + activeMap + "\n";
  s += String("ip         : ") + WiFi.localIP().toString() + "\n";
  s += String("rssi       : ") + WiFi.RSSI() + " dBm\n";
  s += String("psram      : ") + (psramFound() ? "yes" : "no") + "\n";
  s += String("uptime     : ") + (millis() / 1000) + " s\n";
  // Die temperature, not room temperature: this is the SoC's own junction sensor. Useful for
  // judging whether continuous capture + no modem sleep is cooking the module.
  s += String("die temp   : ") + String(temperatureRead(), 1) + " C\n";
  s += String("near  39/38: ") + String(S_NEAR.cm, 1) + " cm" + (S_NEAR.blocked ? "  [SOMEONE]" : "  [clear]  ") +
       "  wakes under " + S_NEAR.thresh + " cm\n";
  s += String("pass  41/40: ") + String(S_PASS.cm, 1) + " cm" + (S_PASS.blocked ? "  [BLOCKED]" : "  [clear]  ") +
       "  counts under " + S_PASS.thresh + " cm\n";
  s += String("passages   : ") + passages + "\n";
  s += "frame      : /shot.jpg\n";
  server.send(200, "text/plain", s);
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("[charon] node " NODE_ID " booting");
  prefs.begin("charon", false);
  S_PASS.thresh = prefs.getInt("passcm", PASS_DIST_CM);
  S_NEAR.thresh = prefs.getInt("wakecm", WAKE_DIST_CM);
  Serial.printf("[charon] pass<%dcm  near<%dcm\n", S_PASS.thresh, S_NEAR.thresh);
  Serial.printf("[charon] psram: %s\n", psramFound() ? "found" : "MISSING (check board flash/psram setting)");

  bool ok = false;
  for (int i = 0; i < N_MAPS && !ok; i++) {
    Serial.printf("[charon] camera map '%s' ... ", MAPS[i].name);
    if (startCamera(MAPS[i])) {
      ok = true;
      activeMap = MAPS[i].name;
      Serial.println("OK");
    } else {
      Serial.println("no");
      esp_camera_deinit();                        // a failed init still claims the pins; release before the next try
      delay(200);
    }
  }
  if (!ok) {
    Serial.println("[charon] no known camera map worked.");
    Serial.println("[charon] check: FPC fully seated + latch closed, camera is OV2640, board really has PSRAM.");
  }

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);                           // modem sleep adds frame latency and hotspot drops; nodes are powered
  for (int i = 0; i < CHARON_AP_COUNT; i++) wifiMulti.addAP(CHARON_APS[i].ssid, CHARON_APS[i].pass);
  Serial.printf("[charon] wifi: trying %d network(s) ", CHARON_AP_COUNT);
  uint32_t t0 = millis();
  while (wifiMulti.run() != WL_CONNECTED && millis() - t0 < 20000) { delay(400); Serial.print("."); }
  Serial.println();
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[charon] wifi FAILED - none in range, wrong password, 5 GHz-only hotspot,");
    Serial.println("[charon] or the network is WPA2-Enterprise (needs 802.1X, not a plain password).");
  } else {
    Serial.printf("[charon] joined '%s'\n", WiFi.SSID().c_str());
    Serial.printf("[charon] ip   http://%s/shot.jpg\n", WiFi.localIP().toString().c_str());
    if (MDNS.begin(NODE_ID)) {                    // survives the hotspot handing out a different IP
      MDNS.addService("http", "tcp", 80);
      Serial.printf("[charon] name http://%s.local/shot.jpg\n", NODE_ID);
    }
    // Password-protected OTA: once this build is on a board over USB, every later change (a new
    // threshold default, a bugfix, a new pin map) ships to a wall-mounted node over wifi. No more
    // pulling six boards off the wall and re-cabling them for a one-line firmware change.
    ArduinoOTA.setHostname(NODE_ID);
    ArduinoOTA.setPassword(OTA_PASSWORD);
    ArduinoOTA.onStart([]() { Serial.println("[charon] OTA update starting..."); });
    ArduinoOTA.onEnd([]()   { Serial.println("[charon] OTA update done, rebooting"); });
    ArduinoOTA.onError([](ota_error_t e) { Serial.printf("[charon] OTA error %u\n", e); });
    ArduinoOTA.begin();
    Serial.println("[charon] OTA ready (network upload, password-protected)");
  }

  for (Sonar *s : {&S_NEAR, &S_PASS}) {
    pinMode(s->trig, OUTPUT); pinMode(s->echo, INPUT); digitalWrite(s->trig, LOW);
  }
  pinMode(LED_GREEN_PIN, OUTPUT); pinMode(LED_RED_PIN, OUTPUT);
  digitalWrite(LED_GREEN_PIN, LOW); digitalWrite(LED_RED_PIN, LOW);

  server.on("/", handleRoot);
  server.on("/shot.jpg", handleShot);
  server.on("/passage", handlePassage);
  server.on("/threshold", handleThreshold);
  server.on("/led", handleLed);
  server.begin();
  Serial.println("[charon] ready");
}

void loop() {
  ArduinoOTA.handle();
  server.handleClient();
  if (ledOffAt && (int32_t)(millis() - ledOffAt) >= 0) {   // self-clearing: a lost "off" never leaves a colour stuck
    digitalWrite(LED_GREEN_PIN, LOW); digitalWrite(LED_RED_PIN, LOW);
    ledOffAt = 0;
  }

  static uint32_t lastPing = 0;
  static bool turn = false;
  if (millis() - lastPing > 35) {         // alternating -> each sonar still gets ~14 reads/s
    lastPing = millis();
    turn = !turn;
    if (turn) { if (pollSonar(S_PASS)) passages++; }   // a body crossed the lane
    else      { pollSonar(S_NEAR); }                   // approach/presence: reported, brain decides
  }

  static uint32_t lastCheck = 0;
  if (millis() - lastCheck > 5000) {              // a node that silently loses wifi is a node the brain calls OFFLINE
    lastCheck = millis();
    if (wifiMulti.run() != WL_CONNECTED) Serial.println("[charon] wifi lost, retrying");
  }
}
