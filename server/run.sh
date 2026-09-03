#!/usr/bin/env bash
# Start the brain the way it actually has to run: reachable from the other devices in the
# demo, not just from this Mac.
#
# Binding to 127.0.0.1 is the easy mistake and it fails in a confusing way - a second browser
# ON the laptop works fine (still loopback) while the phone at the gate cannot connect at all,
# which looks like a phone problem and is not. The demo needs at least two other devices to
# reach this: the gate terminal screen and the phone that films the Telegram token.
set -euo pipefail
cd "$(dirname "$0")"

HOST="${CHARON_HOST:-0.0.0.0}"
PORT="${CHARON_PORT:-8770}"

if [ ! -f .env ]; then
  echo "server/.env missing - copy .env.example and set CHARON_ADMIN_TOKEN"; exit 1
fi

# Refuse to start a second copy rather than failing later with "address already in use",
# which is a confusing way to discover the first one is still running.
if pgrep -f "uvicorn app.main:app" > /dev/null; then
  echo "Charon brain is already running. Stop it first:  ./stop.sh"
  exit 1
fi

# Print the addresses the other devices should actually use, so nobody has to go hunting for
# the laptop's IP on shoot day.
echo "Charon brain starting on ${HOST}:${PORT}"
echo
for ip in $(ipconfig getifaddr en0 2>/dev/null) $(ipconfig getifaddr en1 2>/dev/null); do
  echo "  dashboard      http://${ip}:${PORT}/dashboard/"
  echo "  gate terminal  http://${ip}:${PORT}/gate/?node=gate-in"
  echo "  staff          http://${ip}:${PORT}/staff/"
done
echo "  (on this Mac)  http://127.0.0.1:${PORT}/"
echo

exec .venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT" --app-dir .
