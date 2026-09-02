# Firmware

Two sketches, two very different jobs.

| Sketch | Board | Job |
|---|---|---|
| `charon_node/` | 6x ESP32-S3-WROOM-1 N16R8 + OV5640 | Camera and ultrasonic appliance. Serves frames and sensor readings; makes no access decisions. |
| `uno_watchdog/` | Arduino Uno | Independent gate failover. No network, no laptop. Watches a heartbeat wire and takes over the gate when the smart path dies. |

One `charon_node` image serves all six boards. Identity comes from `NODE_ID` in
`secrets.h`, which the flash scripts rewrite in place per board. The four interior
boards have nothing wired to the PASS pins (41/40), read no echo there, and simply
never report a passage - no separate build needed.

## Setup

```bash
cp secrets.example.h charon_node/secrets.h
chmod 600 charon_node/secrets.h
# then edit: wifi candidates, OTA password
```

`secrets.h` is gitignored and excluded from the OneDrive mirror. Never commit it.

## Flashing

```bash
./flash_node.sh gate-in                          # USB, auto-detects the single plugged-in board
./flash_node.sh zone-workshop /dev/cu.usbmodem101 # USB, explicit port
./ota_node.sh  gate-in                            # wireless, once the board already runs this firmware
```

Both scripts rewrite `#define NODE_ID` in `secrets.h` and recompile, because
identity is baked into the binary. `ota_node.sh` greps the OTA password out of
`secrets.h`, so rotating it there is the whole rotation.

The very first flash of any board must go over USB: OTA needs firmware that already
speaks OTA.

## Build target

```
esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,FlashMode=qio,CDCOnBoot=cdc,PartitionScheme=huge_app
```

- `PSRAM=opi` - these modules carry 8 MB **octal** PSRAM (confirmed with `esptool flash-id`).
  It is the camera frame buffer, and GPIO 33-37 belong to it: touching those pins corrupts
  or crashes the camera.
- `CDCOnBoot=cdc` - the boards enumerate as native USB (`/dev/cu.usbmodemXXXX`), not a UART
  bridge. Without this flag the upload still succeeds but `Serial` output is silently invisible.

## Pin map

Camera routing differs between vendors of this connector style; a wrong map fails as
"camera probe failed (0x105)". The sketch tries the known maps at first boot and pins
the winner in NVS. Confirmed correct on all six of these boards is the `esp32s3-eye` /
Freenove-style routing.

| Signal | GPIO | Signal | GPIO |
|---|---|---|---|
| XCLK | 15 | Y9 (D7) | 16 |
| SIOD | 4 | Y8 (D6) | 17 |
| SIOC | 5 | Y7 (D5) | 18 |
| VSYNC | 6 | Y6 (D4) | 12 |
| HREF | 7 | Y5 (D3) | 10 |
| PCLK | 13 | Y4 (D2) | 8 |
| PWDN | n/c | Y3 (D1) | 9 |
| RESET | n/c | Y2 (D0) | 11 |

Non-camera pins on these boards:

| Use | GPIO |
|---|---|
| NEAR ultrasonic (all six) | trig 39, echo 38 |
| PASS ultrasonic (gate lanes only) | trig 41, echo 40 |
| Heartbeat out to the Arduino (gate-in) | 21 |
| LED green / red (designed, not soldered) | 1 / 2 |
| Free / spare | 42, 47, 48 |

Reserved, do not repurpose: 4-18 camera, 19-20 native USB, 26-32 SPI flash,
**33-37 octal PSRAM**, 0/3/45/46 strapping, 43-44 onboard USB-UART bridge.

The two ultrasonics on a gate board must never fire together: each hears the other's
echo and reports a phantom distance. They are time-multiplexed, one per tick.

## HTTP surface (`charon_node`)

| Route | Purpose |
|---|---|
| `GET /` | Human-readable status: MAC, camera map, IP, RSSI, uptime, die temperature, live distances |
| `GET /status` | Machine-readable JSON, no camera needed. Polled continuously by the brain; carries the passage counter |
| `GET /shot.jpg` | Current frame, with sensor readings piggybacked on the response headers |
| `GET /wake?sec=` | Force the camera awake (dashboard "tap a tile") |
| `GET /threshold?cm=&wake=` | Set and NVS-persist the two sensor thresholds, so a wall-mounted board never needs a cable to recalibrate |
| `GET /led?state=` | Green / red / off, self-clearing after a hold so a dropped "off" cannot leave a colour stuck |

The node never needs to know the brain's address: sensor state rides along on
responses to requests the brain already makes.

## Verifying a freshly flashed board

```bash
curl http://gate-in.local/                 # which camera map won, which MAC answers to this name
curl http://gate-in.local/status           # ssid, cam_on, passages, thresholds
curl -o /tmp/gate-in.jpg http://gate-in.local/shot.jpg
```

The boards are visually identical: the MAC in `/` is the only way to tell which
lump of hardware is answering to which name. Label them physically.
