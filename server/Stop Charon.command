#!/usr/bin/env bash
cd "$(dirname "$0")"
./stop.sh
echo
read -n 1 -s -r -p "Press any key to close this window."
