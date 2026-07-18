#!/usr/bin/env bash
#
# One-way backup mirror: working repo  ->  OneDrive.
#
# IMPORTANT:
#   * This is a BACKUP ONLY. Never run git, never edit files in the OneDrive copy.
#     The working tree at $SRC is always the single source of truth. OneDrive is
#     kept out of the git working path on purpose (its sync can clobber .git
#     mid-operation); this script pushes a snapshot into it one direction only.
#   * Biometric data (server/data, embeddings), secrets, venvs, caches and large
#     ML models are deliberately EXCLUDED so they never land on the corporate
#     school drive (GDPR Art. 9).
#   * .git IS included, so the mirror is a fully restorable clone if the working
#     copy is ever lost.
#
set -euo pipefail

SRC="/Users/home/IdeaProjects/charon-v2/"
DST="/Users/home/Library/CloudStorage/OneDrive-GlobalBankingSchool/Leo/charon-v2/"

mkdir -p "$DST"

rsync -a --delete \
  --exclude '.DS_Store' \
  --exclude 'server/data/' \
  --exclude '**/__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.venv/' --exclude 'venv/' --exclude 'env/' \
  --exclude '*.onnx' \
  --exclude '*.npy' --exclude '*.embeddings' --exclude '*.dat' \
  --exclude '*.db' --exclude '*.db-wal' --exclude '*.db-shm' \
  --exclude '*.sqlite' --exclude '*.sqlite3' \
  --exclude '**/secrets.h' \
  --exclude '**/.tg_token' --exclude '**/.el_key' \
  --exclude 'voice_cache/' --exclude 'voice_samples/' \
  "$SRC" "$DST"

echo "[backup] mirrored $SRC -> $DST at $(date '+%Y-%m-%d %H:%M:%S')"
