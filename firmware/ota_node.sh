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

# arduino-cli finds network ports by IP, not by mDNS hostname, and its own port-discovery
# has to run an mDNS query of its own to do that - separate from, and just as slow as, the
# plain hostname lookup this project already works around elsewhere (see
# app/nodes/resolver.py). The upload command's default discovery window is 1s, which is not
# enough; resolve the IP ourselves first, then give discovery a real window to find it there.
echo "==> resolving $NODE.local"
IP="$(python3 -c "
import socket
try:
    print(socket.getaddrinfo('$NODE.local', None, family=socket.AF_INET, type=socket.SOCK_STREAM)[0][4][0])
except socket.gaierror:
    pass
")"
[ -n "$IP" ] || { echo "$NODE.local did not resolve - is it powered and on the network?"; exit 1; }
echo "    -> $IP"

echo "==> pushing over wifi to $IP (slower than USB - the whole image goes over the air)"
# -F password= (empty) is required even though OTA is unauthenticated: the esp_ota upload
# tool's command template always includes an --auth= field, and arduino-cli refuses to run
# non-interactively without a value for every field the template references.
arduino-cli upload -p "$IP" -l network --fqbn "$FQBN" --discovery-timeout 10s -F password= charon_node
UPLOAD_STATUS=$?

if [ $UPLOAD_STATUS -ne 0 ]; then
  echo
  echo "OTA failed. Known cause on THIS project's demo hotspot (phone-based, SSID 'charon'):"
  echo "the OTA handshake needs a UDP round trip (port 3232) before the image transfers over"
  echo "TCP, and phone hotspots often do not relay client-to-client UDP even though ordinary"
  echo "HTTP (TCP) works fine - confirmed 2026-09-03, see docs/REPORT_NOTES.md. If you are on"
  echo "that hotspot, this is expected: use flash_node.sh over USB instead. If you are on a"
  echo "normal router (home wifi), this is a real failure - investigate."
  exit $UPLOAD_STATUS
fi

echo "==> done. Node reboots on its own once the image is written."
echo "    verify:  curl http://$NODE.local/status"
