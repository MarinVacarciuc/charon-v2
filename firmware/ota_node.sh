#!/bin/bash
# Update one Charon node's firmware over wifi - no USB cable, no taking it off the wall.
# Only works once a board is running firmware that already has ArduinoOTA (this build or later);
# the very first flash of a board must still go over USB via flash_node.sh.
#
#   ./ota_node.sh gate-out
#
# NOTE: OTA on this build is UNAUTHENTICATED. Anyone on the same network can push firmware to
# a node, so only run the nodes on a network you control (the demo hotspot, or home). This is
# an accepted prototype trade-off, not an oversight: see docs/REPORT_NOTES.md.
set -e
cd "$(dirname "$0")"

NODE="${1:?usage: ./ota_node.sh <node-id>}"
FQBN="esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,FlashMode=qio,CDCOnBoot=cdc,PartitionScheme=huge_app"

SEC="charon_node/secrets.h"
[ -f "$SEC" ] || { echo "$SEC missing - copy secrets.example.h to it first"; exit 1; }

echo "==> node '$NODE' is baked into the build (secrets.h NODE_ID); recompiling with that identity"
sed -i '' "s|^#define NODE_ID .*|#define NODE_ID \"$NODE\"|" "$SEC"
grep -q "#define NODE_ID \"$NODE\"" "$SEC" || { echo "failed to set NODE_ID in $SEC"; exit 1; }
arduino-cli compile --fqbn "$FQBN" charon_node

echo "==> pushing over wifi to $NODE.local (slower than USB - the whole image goes over the air)"
arduino-cli upload -p "$NODE.local" -l network --fqbn "$FQBN" charon_node

echo "==> done. Node reboots on its own once the image is written."
echo "    verify:  curl http://$NODE.local/status"
