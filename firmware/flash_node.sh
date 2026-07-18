#!/bin/bash
# Flash one Charon node with its identity.
#   ./flash_node.sh gate-out            (auto-detects the single plugged-in board)
#   ./flash_node.sh zone-workshop /dev/cu.usbmodemXXXX
#
# The node id is baked in per board: it names the node to the brain and becomes its
# mDNS name (<id>.local). Planned set:
#   gate-in  gate-out  zone-reception  zone-warehouse  zone-workshop  zone-server
set -e
cd "$(dirname "$0")"

NODE="${1:?usage: ./flash_node.sh <node-id> [port]}"
PORT="${2:-$(ls /dev/cu.usbmodem* 2>/dev/null | head -1)}"
[ -n "$PORT" ] || { echo "no board found - plug one in (USB-C)"; exit 1; }

# Board is ESP32-S3-WROOM-1 N16R8: 16MB quad flash + 8MB octal PSRAM (confirmed via esptool flash-id).
# CDCOnBoot=cdc is required to see Serial over the native USB port.
FQBN="esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,FlashMode=qio,CDCOnBoot=cdc,PartitionScheme=huge_app"

SEC="charon_node/secrets.h"
[ -f "$SEC" ] || { echo "$SEC missing - copy secrets.example.h to it and add your wifi"; exit 1; }

echo "==> node '$NODE' on $PORT"
sed -i '' "s|^#define NODE_ID .*|#define NODE_ID \"$NODE\"|" "$SEC"
grep -q "#define NODE_ID \"$NODE\"" "$SEC" || { echo "could not set NODE_ID in $SEC"; exit 1; }

arduino-cli compile --fqbn "$FQBN" charon_node
arduino-cli upload -p "$PORT" --fqbn "$FQBN" charon_node

echo
echo "==> flashed. give it ~10s to join wifi, then:"
echo "    curl http://$NODE.local/          # status + which camera pin map won"
echo "    curl -o /tmp/$NODE.jpg http://$NODE.local/shot.jpg"
