# firmware — ESP32-S3 nodes

Two roles run on ESP32-S3 boards:

- **Gate wake node** — an HC-SR04 ultrasonic sensor in a low-power loop. When a person comes within `TRIGGER_DIST_CM`, it sends a UDP packet to the gate server (the S10) to wake the face pipeline. This also satisfies the brief's ultrasound + alarm requirement.
- **Zone nodes** — watch an interior zone, wake their camera on presence for energy efficiency, and store-and-forward to microSD when the network drops.

## Setup

1. Copy `secrets.example.h` to `secrets.h` and fill in WiFi, server IP/port and the node id.
2. `secrets.h` is gitignored — never commit it.
3. Build target and pin map: to be documented as the code lands.
