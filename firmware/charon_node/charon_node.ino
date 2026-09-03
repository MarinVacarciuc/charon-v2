/*
  Charon node - firmware v2 (gate / zone camera + ultrasonic appliance).

  The node makes no decisions. It reports what its sensors read and, when someone is
  actually there, what its camera sees. All policy lives in the brain.

  Three things changed from v1, each for a stated reason:

  1. The camera is OFF until the near sensor says someone is here. Cameras that do not
     record until a person is present is the privacy-by-design and energy story, and it
     is cheap: WiFi stays up, which also keeps the 18650 boost bank above its
     low-current auto-cutoff (a true deep sleep trips that cutoff on this exact power
     hardware - measured, not theorised).

  2. /status serves the sensor and health picture as JSON without touching the camera,
     so the brain can poll every node continuously while five of six cameras stay dark.
     The passage counter rides on it, which is what commits an entry or exit.

  3. A heartbeat square wave on GPIO 21 says "the smart path is alive": this board is
     up, on WiFi, AND has heard from the brain recently. An Arduino Uno at the gate
     watches this one wire and takes the gate over when it stops. Crashing, losing
     WiFi and the brain dying all collapse it identically, which is the point.

  Camera routing differs between vendors of this connector style, so boot probes the
  known maps and pins the winner in NVS; later wakes use the pinned map directly and
  re-probe only if it ever stops working.
*/
#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiMulti.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include <Preferences.h>
#include <ArduinoOTA.h>
#include "secrets.h"

#define FW_VERSION "2.0.0"

// Thresholds depend on the geometry of the spot each node ends up in, which is not known
// at flash time. Settable over HTTP and persisted in NVS: six nodes on six walls must not
// each need a USB cable to be recalibrated. secrets.h values are first-boot defaults only.
Preferences prefs;

WiFiMulti wifiMulti;

// Only the gate lanes have a second sensor soldered to 41/40. On an interior board those
// pins read no echo, and every poll of them would block the full pulseIn timeout (25 ms)
// for nothing. Identity is baked in at flash time, so decide once at boot.
static bool hasPass = false;

// RCWL-1601 ultrasonics, powered from 3V3 so their echo is 3.3V logic straight into a GPIO
// - no divider (an HC-SR04 at 5V would need one). Free pins here: the camera holds 4-18,
// octal PSRAM holds 33-37, flash 26-32, USB 19/20.
//
// NEAR (39/38) means the same thing on every node: "someone is here". At the gate it wakes
// the camera; in a zone it wakes the camera and nothing else. PASS (41/40) exists only on
// the gate lanes and means a body actually crossed the lane - that is the event the brain
// commits an entry or exit on.
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

// Access-decision LEDs. GPIO1/2 are free on every one of these boards (not camera, not
// octal PSRAM/flash, not USB, not a strapping pin). Designed and driven here; not
// currently soldered, which costs nothing - the brain's calls are simply invisible.
#define LED_GREEN_PIN 1
#define LED_RED_PIN   2
#define LED_HOLD_MS   3000
static uint32_t ledOffAt = 0;

// Heartbeat to the Arduino Uno failover at the gate. 3.3V out into a 5V-tolerant Uno
// input, one direction only, never the reverse. A square wave rather than a level so a
// stuck-high pin cannot masquerade as a healthy system.
#define HB_PIN            21
#define HB_HALF_PERIOD_MS 500      // -> 1 Hz
#define HB_BRAIN_TIMEOUT_MS 5000   // no brain contact this long = the smart path is down
static bool     hbLevel = false;
static uint32_t hbToggledAt = 0;
static uint32_t lastBrainMs = 0;   // 0 = the brain has never spoken to us since boot

// Camera power state. Waking costs about a second of re-init, which is why the near
// sensor wakes it rather than the first frame request.
#define CAM_IDLE_MS 20000
static bool     camOn = false;
static uint32_t camIdleAt = 0;

static volatile uint32_t passages = 0;   // monotonic; the brain watches this increment

struct PinMap {
  const char *name;
  int8_t pwdn, reset, xclk, siod, sioc;
  int8_t y9, y8, y7, y6, y5, y4, y3, y2;
  int8_t vsync, href, pclk;
};

// Taken verbatim from the Arduino esp32 core camera_pins.h (v3.3.8). The S3-EYE routing is
// what most generic "ESP32-S3 WROOM CAM" boards clone, so it is tried first, and it is the
// one confirmed working on all six of these boards.
static const PinMap MAPS[] = {
  {"esp32s3-eye / freenove-s3-wroom", -1, -1, 15,  4,  5, 16, 17, 18, 12, 10,  8,  9, 11,  6,  7, 13},
  {"xiao-esp32s3-sense",              -1, -1, 10, 40, 39, 48, 11, 12, 14, 16, 18, 17, 15, 38, 47, 13},
  {"esp32s3-cam-lcd",                 -1, -1, 40, 17, 18, 39, 41, 42, 12,  3, 14, 47, 13, 21, 38, 11},
};
static const int N_MAPS = sizeof(MAPS) / sizeof(MAPS[0]);
static int pinnedMap = -1;                       // index into MAPS, remembered in NVS

WebServer server(80);

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
  c.frame_size   = FRAMESIZE_VGA;                 // 640x480 - the Mac does the recognition
  c.jpeg_quality = 12;
  c.fb_count     = psramFound() ? 2 : 1;
  c.fb_location  = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  c.grab_mode    = CAMERA_GRAB_LATEST;            // newest frame, never a queued stale one
  return esp_camera_init(&c) == ESP_OK;
}

// Probe every known map and remember the winner, so a wake never pays for three attempts.
static bool probeAndPinMap() {
  for (int i = 0; i < N_MAPS; i++) {
    Serial.printf("[charon] camera map '%s' ... ", MAPS[i].name);
    if (startCamera(MAPS[i])) {
      Serial.println("OK");
      pinnedMap = i;
      prefs.putInt("cammap", i);
      return true;                                 // leaves the camera INITIALISED
    }
    Serial.println("no");
    esp_camera_deinit();                           // a failed init still claims the pins
    delay(200);
  }
  Serial.println("[charon] no known camera map worked.");
  Serial.println("[charon] check: FPC fully seated + latch closed, board really has PSRAM.");
  return false;
}

// Push the sleep deadline out, never pull it in. Several things ask to keep the camera
// awake - a near trip, a frame request, an explicit /wake hold - and they must not be able
// to cut each other short. Without this, a dashboard asking for a 5 minute hold would be
// silently reduced to 20 seconds by the first person who walked past the sensor.
static void keepCameraAwakeFor(uint32_t ms) {
  uint32_t want = millis() + ms;
  if (!camOn || (int32_t)(want - camIdleAt) > 0) camIdleAt = want;
}

static bool cameraWake() {
  if (camOn) { keepCameraAwakeFor(CAM_IDLE_MS); return true; }
  bool ok = false;
  if (pinnedMap >= 0) {
    ok = startCamera(MAPS[pinnedMap]);
    if (!ok) {
      // The pinned map stopped working (swapped module, reseated ribbon). Re-probe rather
      // than staying blind forever.
      Serial.println("[charon] pinned camera map failed, re-probing");
      esp_camera_deinit();
      delay(200);
      ok = probeAndPinMap();
    }
  } else {
    ok = probeAndPinMap();
  }
  if (ok) {
    camOn = true;
    camIdleAt = millis() + CAM_IDLE_MS;   // fresh wake: this IS the deadline, not an extension
    Serial.printf("[charon] camera ON (%s)\n", MAPS[pinnedMap].name);
  }
  return ok;
}

static void cameraSleep() {
  if (!camOn) return;
  esp_camera_deinit();
  camOn = false;
  Serial.printf("[charon] camera OFF (idle) heap=%u\n", (unsigned)ESP.getFreeHeap());
}

static float readDistanceCm(const Sonar &s) {
  digitalWrite(s.trig, LOW);  delayMicroseconds(3);
  digitalWrite(s.trig, HIGH); delayMicroseconds(10);
  digitalWrite(s.trig, LOW);
  unsigned long us = pulseIn(s.echo, HIGH, 25000UL);   // ~4 m ceiling; 0 = no echo came back
  return us ? us / 58.0f : -1.0f;
}

// Two ultrasonics on one board must never ping together or each hears the other's echo and
// reports a phantom wall. So exactly one fires per tick and they alternate.
//
// HYSTERESIS: a single trip distance is not enough. Clutter/multipath near the threshold
// (measured live: readings bouncing 17-65 cm around a 60 cm threshold) crosses one boundary
// back and forth on pure noise, counting a "passage" every time - 6 phantom counts in 8
// seconds with nobody there. So the clearing distance is pushed HYST_CM further out than
// the tripping distance: once blocked, it stays blocked until the reading is unambiguously
// clear. Two agreeing readings still debounce a single noisy sample before any transition.
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

// Any request from the brain is proof the brain is alive. That, plus our own WiFi state,
// is exactly what the heartbeat asserts.
static void noteBrainContact() { lastBrainMs = millis(); }

static void handleStatus() {
  noteBrainContact();
  String s = "{";
  s += "\"node\":\"" NODE_ID "\"";
  s += ",\"fw\":\"" FW_VERSION "\"";
  s += ",\"mac\":\"" + WiFi.macAddress() + "\"";
  s += ",\"ssid\":\"" + WiFi.SSID() + "\"";        // joining the wrong network must be visible, not silent
  s += ",\"rssi\":" + String(WiFi.RSSI());
  s += ",\"ip\":\"" + WiFi.localIP().toString() + "\"";
  s += ",\"uptime_s\":" + String(millis() / 1000);
  s += ",\"heap\":" + String((unsigned)ESP.getFreeHeap());
  s += ",\"die_c\":" + String(temperatureRead(), 1);
  s += ",\"cam_on\":" + String(camOn ? "true" : "false");
  s += ",\"cam_map\":\"" + String(pinnedMap >= 0 ? MAPS[pinnedMap].name : "none") + "\"";
  s += ",\"has_pass\":" + String(hasPass ? "true" : "false");
  s += ",\"passages\":" + String(passages);
  s += ",\"near_cm\":" + String(S_NEAR.cm, 1);
  s += ",\"near\":" + String(S_NEAR.blocked ? "true" : "false");
  s += ",\"wake_cm\":" + String(S_NEAR.thresh);
  s += ",\"pass_cm\":" + String(S_PASS.cm, 1);
  s += ",\"pass_blocked\":" + String(S_PASS.blocked ? "true" : "false");
  s += ",\"pass_thresh_cm\":" + String(S_PASS.thresh);
  s += "}";
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", s);
}

static void handleShot() {
  noteBrainContact();
  if (!camOn && !cameraWake()) {
    server.sendHeader("X-Cam-On", "0");
    server.send(503, "text/plain", "camera unavailable");
    return;
  }
  keepCameraAwakeFor(CAM_IDLE_MS);
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    server.sendHeader("X-Cam-On", "1");
    server.send(503, "text/plain", "no frame");
    return;
  }
  // The brain already polls this, so sensor state rides along in the headers: no second
  // request, and the node never needs to know the brain's (changing) address.
  server.sendHeader("X-Passage", String(passages));
  server.sendHeader("X-Dist-Cm", String(S_PASS.cm, 1));
  server.sendHeader("X-Near-Cm", String(S_NEAR.cm, 1));
  server.sendHeader("X-Near", S_NEAR.blocked ? "1" : "0");
  server.sendHeader("X-Cam-On", "1");
  server.sendHeader("X-Node", NODE_ID);
  server.setContentLength(fb->len);
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "image/jpeg", "");
  server.sendContent((const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

// Pre-warm a camera the near sensor has not tripped: the dashboard's "tap a sleeping tile"
// needs a live picture without waiting for someone to walk up to the board.
static void handleWake() {
  noteBrainContact();
  int sec = server.hasArg("sec") ? server.arg("sec").toInt() : 30;
  if (sec < 1)   sec = 1;
  if (sec > 300) sec = 300;
  bool ok = cameraWake();
  // An explicit operator request SETS the deadline rather than extending it: asking for a
  // short look must actually give a short look, or the reported for_s is a lie. This does
  // not strand anyone standing in front of the sensor - the near-sensor refresh in loop()
  // pushes the deadline back out on the very next tick while they are still there.
  if (ok) camIdleAt = millis() + (uint32_t)sec * 1000UL;
  server.send(ok ? 200 : 503, "application/json",
              String("{\"cam_on\":") + (ok ? "true" : "false") +
              ",\"for_s\":" + sec + "}");
}

static void handleLed() {
  noteBrainContact();
  String st = server.arg("state");
  digitalWrite(LED_GREEN_PIN, st == "green" ? HIGH : LOW);
  digitalWrite(LED_RED_PIN,   st == "red"   ? HIGH : LOW);
  ledOffAt = (st == "green" || st == "red") ? millis() + LED_HOLD_MS : 0;
  server.send(200, "text/plain", "led: " + st);
}

// Calibrate in place: /threshold?cm=60&wake=250 . Persisted, so it survives a reboot or a
// flat battery. Six boards on six walls, none of them reachable with a USB cable.
static void handleThreshold() {
  noteBrainContact();
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
              String("{\"pass_thresh_cm\":") + S_PASS.thresh + ",\"pass_cm\":" + String(S_PASS.cm, 1) +
              ",\"wake_cm\":" + S_NEAR.thresh + ",\"near_cm\":" + String(S_NEAR.cm, 1) + "}");
}

static void handleRoot() {
  noteBrainContact();
  String s = String("charon node: ") + NODE_ID + "  (fw " FW_VERSION ")\n";
  // The boards are physically identical and the identity lives only in flash, so print the
  // MAC: it is the only way to tell which lump of hardware answers to which name.
  s += String("mac        : ") + WiFi.macAddress() + "\n";
  s += String("camera map : ") + (pinnedMap >= 0 ? MAPS[pinnedMap].name : "none") +
       (camOn ? "  [ON]\n" : "  [asleep]\n");
  s += String("ssid       : ") + WiFi.SSID() + "\n";
  s += String("ip         : ") + WiFi.localIP().toString() + "\n";
  s += String("rssi       : ") + WiFi.RSSI() + " dBm\n";
  s += String("psram      : ") + (psramFound() ? "yes" : "no") + "\n";
  s += String("heap       : ") + (unsigned)ESP.getFreeHeap() + " B\n";
  s += String("uptime     : ") + (millis() / 1000) + " s\n";
  // Die temperature, not room temperature: the SoC's own junction sensor.
  s += String("die temp   : ") + String(temperatureRead(), 1) + " C\n";
  s += String("heartbeat  : ") + (lastBrainMs && millis() - lastBrainMs < HB_BRAIN_TIMEOUT_MS
                                  ? "pulsing (brain heard from)" : "SILENT (no brain contact)") + "\n";
  s += String("near  39/38: ") + String(S_NEAR.cm, 1) + " cm" + (S_NEAR.blocked ? "  [SOMEONE]" : "  [clear]  ") +
       "  wakes under " + S_NEAR.thresh + " cm\n";
  if (hasPass) {
    s += String("pass  41/40: ") + String(S_PASS.cm, 1) + " cm" + (S_PASS.blocked ? "  [BLOCKED]" : "  [clear]  ") +
         "  counts under " + S_PASS.thresh + " cm\n";
    s += String("passages   : ") + passages + "\n";
  } else {
    s += "pass  41/40: not fitted on this node (interior board)\n";
  }
  s += "status     : /status\nframe      : /shot.jpg\n";
  server.send(200, "text/plain", s);
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("[charon] node " NODE_ID " fw " FW_VERSION " booting");

  hasPass = (strncmp(NODE_ID, "gate", 4) == 0);
  Serial.printf("[charon] role: %s\n", hasPass ? "gate lane (near + pass)" : "interior zone (near only)");

  prefs.begin("charon", false);
  S_PASS.thresh = prefs.getInt("passcm", PASS_DIST_CM);
  S_NEAR.thresh = prefs.getInt("wakecm", WAKE_DIST_CM);
  pinnedMap     = prefs.getInt("cammap", -1);
  Serial.printf("[charon] pass<%dcm  near<%dcm\n", S_PASS.thresh, S_NEAR.thresh);
  Serial.printf("[charon] psram: %s\n", psramFound() ? "found" : "MISSING (check board flash/psram setting)");

  // Probe once at first boot to learn and remember the map, then put the camera straight
  // back to sleep: nothing should be recording until someone is actually here.
  if (pinnedMap < 0) {
    if (probeAndPinMap()) { camOn = true; cameraSleep(); }
  } else {
    Serial.printf("[charon] camera map pinned: %s (asleep until someone approaches)\n", MAPS[pinnedMap].name);
  }

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);                           // modem sleep adds frame latency and hotspot drops

  // PREFERRED network first, explicitly. WiFiMulti on its own joins whichever candidate is
  // STRONGEST, which is not the same as the one that is correct: on shoot day a house
  // router nearer the gate than the phone hotspot would pull some boards onto the home
  // network while others joined the hotspot, and the laptop can only sit on one of them.
  // Half the nodes would then read OFFLINE with nothing on screen explaining why. Trying
  // CHARON_APS[0] by name first removes that by construction; the rest stay as fallbacks.
  Serial.printf("[charon] wifi: preferred '%s' ", CHARON_APS[0].ssid);
  WiFi.begin(CHARON_APS[0].ssid, CHARON_APS[0].pass);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 8000) { delay(400); Serial.print("."); }
  Serial.println();

  if (WiFi.status() != WL_CONNECTED && CHARON_AP_COUNT > 1) {
    Serial.printf("[charon] preferred not available, falling back to %d other network(s) ",
                  CHARON_AP_COUNT - 1);
    WiFi.disconnect();
    for (int i = 1; i < CHARON_AP_COUNT; i++) wifiMulti.addAP(CHARON_APS[i].ssid, CHARON_APS[i].pass);
    t0 = millis();
    while (wifiMulti.run() != WL_CONNECTED && millis() - t0 < 12000) { delay(400); Serial.print("."); }
    Serial.println();
  }
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[charon] wifi FAILED - none in range, wrong password, 5 GHz-only hotspot,");
    Serial.println("[charon] or the network is WPA2-Enterprise (needs 802.1X, not a plain password).");
  } else {
    Serial.printf("[charon] joined '%s' (%d dBm)\n", WiFi.SSID().c_str(), WiFi.RSSI());
    Serial.printf("[charon] ip   http://%s/status\n", WiFi.localIP().toString().c_str());
    if (MDNS.begin(NODE_ID)) {                    // survives the hotspot handing out a different IP
      MDNS.addService("http", "tcp", 80);
      Serial.printf("[charon] name http://%s.local/status\n", NODE_ID);
    }
    // OTA is deliberately UNAUTHENTICATED on this build. Anyone on the same network can
    // push firmware to a node. That is an accepted risk for a prototype that only ever runs
    // on a private phone hotspot, and it buys back a real hazard: a password baked into the
    // image has to stay in sync with secrets.h, and any mismatch locks the board out of
    // wireless updates and forces it off the wall for a USB flash. Authenticated OTA, and
    // signed images, are written up as designed-not-built - see docs/REPORT_NOTES.md.
    ArduinoOTA.setHostname(NODE_ID);
    ArduinoOTA.onStart([]() {
      // Flash writes and camera DMA do not mix; drop the camera before taking an image.
      cameraSleep();
      Serial.println("[charon] OTA update starting...");
    });
    ArduinoOTA.onEnd([]()   { Serial.println("[charon] OTA update done, rebooting"); });
    ArduinoOTA.onError([](ota_error_t e) { Serial.printf("[charon] OTA error %u\n", e); });
    ArduinoOTA.begin();
    Serial.println("[charon] OTA ready (network upload, password-protected)");
  }

  pinMode(S_NEAR.trig, OUTPUT); pinMode(S_NEAR.echo, INPUT); digitalWrite(S_NEAR.trig, LOW);
  if (hasPass) { pinMode(S_PASS.trig, OUTPUT); pinMode(S_PASS.echo, INPUT); digitalWrite(S_PASS.trig, LOW); }

  pinMode(LED_GREEN_PIN, OUTPUT); pinMode(LED_RED_PIN, OUTPUT);
  digitalWrite(LED_GREEN_PIN, LOW); digitalWrite(LED_RED_PIN, LOW);

  pinMode(HB_PIN, OUTPUT); digitalWrite(HB_PIN, LOW);

  server.on("/",          handleRoot);
  server.on("/status",    handleStatus);
  server.on("/shot.jpg",  handleShot);
  server.on("/wake",      handleWake);
  server.on("/threshold", handleThreshold);
  server.on("/led",       handleLed);
  server.begin();
  Serial.println("[charon] ready");
}

void loop() {
  ArduinoOTA.handle();
  server.handleClient();

  if (ledOffAt && (int32_t)(millis() - ledOffAt) >= 0) {   // a lost "off" never leaves a colour stuck
    digitalWrite(LED_GREEN_PIN, LOW); digitalWrite(LED_RED_PIN, LOW);
    ledOffAt = 0;
  }

  // Heartbeat. Deliberately conjunctive: our own radio AND recent proof the brain is
  // there. Any single failure in the smart path stops the wave, and the Uno cannot tell
  // (or care) which one it was.
  bool smartPathUp = (WiFi.status() == WL_CONNECTED) &&
                     lastBrainMs && (millis() - lastBrainMs < HB_BRAIN_TIMEOUT_MS);
  if (!smartPathUp) {
    if (hbLevel) { hbLevel = false; digitalWrite(HB_PIN, LOW); }
  } else if (millis() - hbToggledAt >= HB_HALF_PERIOD_MS) {
    hbToggledAt = millis();
    hbLevel = !hbLevel;
    digitalWrite(HB_PIN, hbLevel ? HIGH : LOW);
  }

  static uint32_t lastPing = 0;
  static bool turn = false;
  if (millis() - lastPing > 35) {
    lastPing = millis();
    if (hasPass) {
      turn = !turn;
      if (turn) { if (pollSonar(S_PASS)) passages++; }   // a body crossed the lane
      else      { if (pollSonar(S_NEAR)) cameraWake(); } // approach: wake, do not decide
    } else {
      if (pollSonar(S_NEAR)) cameraWake();               // interior board: near only
    }
    // Someone still standing there keeps the camera alive without re-triggering. Extends
    // only: a person walking past must not cut short a longer hold the dashboard asked for.
    if (S_NEAR.blocked && camOn) keepCameraAwakeFor(CAM_IDLE_MS);
  }

  if (camOn && (int32_t)(millis() - camIdleAt) >= 0) cameraSleep();

  // A node that silently loses wifi reads OFFLINE to the brain, so keep retrying - but
  // retry the PREFERRED network first for the same reason it is preferred at boot.
  // Without this, a node that briefly drops the hotspot settles onto the house network
  // and never comes back, which looks identical to a dead board.
  static uint32_t lastCheck = 0;
  if (millis() - lastCheck > 5000) {
    lastCheck = millis();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[charon] wifi lost, retrying preferred first");
      WiFi.begin(CHARON_APS[0].ssid, CHARON_APS[0].pass);
    } else if (CHARON_AP_COUNT > 1 && WiFi.SSID() != String(CHARON_APS[0].ssid)) {
      // Connected, but to a fallback. If the preferred network has come back (the phone
      // hotspot was switched on late), move to it rather than staying split from the brain.
      int n = WiFi.scanComplete();
      if (n == WIFI_SCAN_FAILED) { WiFi.scanNetworks(true); }
      else if (n > 0) {
        for (int i = 0; i < n; i++) {
          if (WiFi.SSID(i) == String(CHARON_APS[0].ssid)) {
            Serial.printf("[charon] preferred '%s' is back, switching\n", CHARON_APS[0].ssid);
            WiFi.disconnect();
            WiFi.begin(CHARON_APS[0].ssid, CHARON_APS[0].pass);
            break;
          }
        }
        WiFi.scanDelete();
      }
    }
  }
}
