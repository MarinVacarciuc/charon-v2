#pragma once
// TEMPLATE. Copy to charon_node/secrets.h and fill in. secrets.h is gitignored,
// excluded from the OneDrive mirror, and must never be committed.
//
//   cp secrets.example.h charon_node/secrets.h && chmod 600 charon_node/secrets.h

// Networks this node may join. WiFiMulti picks the STRONGEST candidate, not the
// intended one. Keep this list SHORT: an unrelated AP that happens to be closer
// will silently outrank the network you meant to use, and six wall-mounted boards
// on the wrong SSID look identical to six dead boards. List only the networks the
// node genuinely needs, and prune before a demo.
//
// Two hardware facts that decide what belongs here:
//   * The ESP32 has no 5 GHz radio. On a band-split router only the "<name>_2g"
//     half is ever visible; listing the 5 GHz name just adds a candidate that
//     always fails.
//   * WPA2-Enterprise (802.1X, user + password, e.g. most campus networks) cannot
//     be joined with a plain PSK at all.
struct CharonAp { const char *ssid; const char *pass; };
static const CharonAp CHARON_APS[] = {
  {"YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD"},
};
static const int CHARON_AP_COUNT = sizeof(CHARON_APS) / sizeof(CHARON_APS[0]);

// NOTE: there is no OTA password. Wireless updates on this build are unauthenticated,
// which is an accepted prototype risk on a private network. See docs/REPORT_NOTES.md.

// This node's identity, also its mDNS name: <NODE_ID>.local
// flash_node.sh and ota_node.sh rewrite this line in place per board, so whatever
// is here is only the value of the last flash.
// Set: gate-in, gate-out, zone-reception, zone-warehouse, zone-workshop, zone-server
#define NODE_ID "gate-in"

// PASS sensor (41/40) - gate lanes only; the four interior boards have nothing
// wired to these pins and simply never report a passage. Closer than this across
// the lane counts as a body crossing, which is what commits an entry or exit.
// First-boot default only: the live value is set over HTTP and persisted in NVS,
// and must be calibrated at the real mounting spot. Desk calibration does not
// transfer (measured: 13-200 cm frame-to-frame from multipath on a cluttered desk).
#define PASS_DIST_CM 100

// NEAR sensor (39/38) - every node. Closer than this = someone is here, wake the
// camera. Allow for the ~1 s camera re-init: 2.5 m gives a walking person about a
// second of margin before they are in frame.
#define WAKE_DIST_CM 250
