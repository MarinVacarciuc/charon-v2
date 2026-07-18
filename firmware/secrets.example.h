#pragma once
// Copy this file to `secrets.h` next to the sketch and fill in real values.
// `secrets.h` is gitignored and must never be committed.

// Networks the node may join; strongest available wins (WiFiMulti). List every network the
// node will ever see (home, demo hotspot, site) so demo day needs no reflash.
// ESP32 is 2.4 GHz only: a 5 GHz-only hotspot is invisible to it, and a WPA2-Enterprise
// network (802.1X username+password) will not work with a plain PSK like this.
struct CharonAp { const char *ssid; const char *pass; };
static const CharonAp CHARON_APS[] = {
  {"YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD"},
};
static const int CHARON_AP_COUNT = sizeof(CHARON_APS) / sizeof(CHARON_APS[0]);

// This node's identity. Also its mDNS name: <NODE_ID>.local
// Planned set: gate-in, gate-out, zone-reception, zone-warehouse, zone-workshop, zone-server
#define NODE_ID "gate-in"

// Anything closer than this across the lane counts as a body passing. Calibrate per node.
#define PASS_DIST_CM 100

// Approach/presence sensor (39/38): closer than this = someone is here.
#define WAKE_DIST_CM 250

#define OTA_PASSWORD "changeme"
