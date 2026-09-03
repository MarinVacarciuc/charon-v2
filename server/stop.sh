#!/usr/bin/env bash
# Stop the brain. Safe to run when nothing is running.
PIDS=$(pgrep -f "uvicorn app.main:app" || true)
if [ -z "$PIDS" ]; then
  echo "Charon brain is not running."
  exit 0
fi
kill $PIDS 2>/dev/null || true
sleep 1
# Anything that ignored a polite stop gets a firm one, so a half-dead process cannot hold
# port 8770 and make the next start fail for a reason nobody can see.
STILL=$(pgrep -f "uvicorn app.main:app" || true)
[ -n "$STILL" ] && kill -9 $STILL 2>/dev/null || true
echo "Charon brain stopped."
