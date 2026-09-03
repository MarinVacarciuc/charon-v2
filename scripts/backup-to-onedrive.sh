#!/usr/bin/env bash
#
# One-way backup mirror: working repo  ->  OneDrive.
#
# IMPORTANT:
#   * This is a BACKUP ONLY. Never run git, never edit files in the OneDrive copy.
#     The working tree at $SRC is always the single source of truth. OneDrive is
#     kept out of the git working path on purpose (its sync can clobber .git
#     mid-operation); this script pushes a snapshot into it one direction only.
#   * The destination is a CORPORATE school drive. Biometric data, secrets, venvs,
#     caches and large ML models must never land there (UK GDPR Art. 9). The
#     exclude list below is therefore kept a superset of .gitignore: gitignored is
#     not enough, because an untracked staff/ directory or a .env file would still
#     be picked up by a plain file mirror.
#   * .git IS included, so the mirror is a fully restorable clone if the working
#     copy is ever lost.
#
# rsync applies the FIRST matching rule, so the two --include lines that keep the
# committed template files must stay above the --exclude patterns that would
# otherwise swallow them.
#
set -euo pipefail

SRC="/Users/home/IdeaProjects/charon-v2/"
DST="/Users/home/Library/CloudStorage/OneDrive-GlobalBankingSchool/Leo/charon-v2/"

mkdir -p "$DST"

rsync -a --delete --delete-excluded \
  --include '*.example.h' \
  --include '.env.example' \
  \
  `# --- biometric / personal data (GDPR Art. 9) ---` \
  --exclude 'server/data/' \
  --exclude 'prototype/staff/' --exclude 'charon-spikes/staff/' --exclude '**/staff_db/' \
  --exclude '**/faces/' --exclude '**/known_faces/' --exclude '**/enrolled/' \
  --exclude '**/captures/' \
  --exclude '*.npy' --exclude '*.embeddings' --exclude '*.dat' \
  --exclude '*.db' --exclude '*.db-wal' --exclude '*.db-shm' \
  --exclude '*.sqlite' --exclude '*.sqlite3' \
  \
  `# --- secrets ---` \
  --exclude '*secret*' \
  --exclude '.env' --exclude '.env.*' \
  --exclude '*.key' --exclude '*.pem' \
  --exclude 'config.local.*' \
  --exclude '**/.tg_token' --exclude '**/.el_key' \
  \
  `# --- large / regenerable artefacts ---` \
  --exclude 'server/models/' --exclude '*.onnx' \
  --exclude '**/haarcascade_*.xml' \
  --exclude 'server/voice/' --exclude 'voice_cache/' --exclude 'voice_samples/' \
  --exclude '.venv/' --exclude 'venv/' --exclude 'env/' \
  --exclude '**/__pycache__/' --exclude '*.pyc' --exclude '*.egg-info/' \
  --exclude '.pio/' --exclude 'build/' --exclude '*.bin' --exclude '*.elf' \
  --exclude '*.log' \
  \
  `# --- editor / OS noise ---` \
  --exclude '.DS_Store' --exclude 'Thumbs.db' \
  --exclude '.vscode/' --exclude '.idea/' \
  \
  "$SRC" "$DST"

# Fail loudly rather than silently leaking: if anything in a forbidden class made
# it across, say so. A backup that quietly ships biometrics is worse than none.
LEAKS="$(find "$DST" \( -name '*.npy' -o -name '*.db' -o -name '*.sqlite*' \
                     -o -name '.env' -o -name 'secrets.h' -o -name '*.key' -o -name '*.pem' \) \
                     -not -path '*/.git/*' 2>/dev/null || true)"
if [ -n "$LEAKS" ]; then
  echo "[backup] REFUSING TO CLAIM SUCCESS - forbidden files present in the mirror:" >&2
  echo "$LEAKS" >&2
  exit 1
fi

echo "[backup] mirrored $SRC -> $DST at $(date '+%Y-%m-%d %H:%M:%S')"
