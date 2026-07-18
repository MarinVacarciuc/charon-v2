#!/bin/bash
# Update one Charon node's firmware over wifi - no USB cable, no taking it off the wall.
# Only works once a board is running firmware that already has ArduinoOTA (this build or later);
# the very first flash of a board must still go over USB via flash_node.sh.
#
#   ./ota_node.sh gate-out
#
set -e
cd "$(dirname "$0")"

NODE="${1:?usage: ./ota_node.sh <node-id>}"
FQBN="esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,FlashMode=qio,CDCOnBoot=cdc,PartitionScheme=huge_app"

SEC="charon_node/secrets.h"
[ -f "$SEC" ] || { echo "$SEC missing"; exit 1; }
PASS=$(grep -oE '#define OTA_PASSWORD "[^"]*"' "$SEC" | sed -E 's/.*"(.*)"/\1/')
[ -n "$PASS" ] || { echo "OTA_PASSWORD not found in $SEC"; exit 1; }

echo "==> node '$NODE' now baked into the build (secrets.h NODE_ID); recompiling with that identity"
sed -i '' "s|^#define NODE_ID .*|#define NODE_ID \"$NODE\"|" "$SEC"
arduino-cli compile --fqbn "$FQBN" charon_node

echo "==> pushing over wifi to $NODE.local (this takes longer than USB - full image over the air)"
arduino-cli upload -p "$NODE.local" -l network --fqbn "$FQBN" --upload-field password="$PASS" charon_node

echo "==> done. Node reboots on its own once the image is written."
