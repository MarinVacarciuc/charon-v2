#!/usr/bin/env bash
# Push the repo (branch + tags) to GitHub after every commit.
#
# Never blocks the commit: a failure here (no network, working offline in the yard) is
# reported but ignored, same discipline as backup-to-onedrive.sh. This is a SECOND, offsite
# backup alongside the OneDrive mirror - not a replacement for it, since GitHub needs a
# network connection the OneDrive mirror does not.
#
# Tags are pushed explicitly (--tags) because they ARE the P6 iteration evidence
# (v0-baseline .. v4.2-ui) and a plain push does not carry new tags by default.
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"
cd "$REPO"

if ! git remote get-url origin > /dev/null 2>&1; then
  echo "[post-commit] no 'origin' remote configured - skipping GitHub push"
  exit 0
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git push origin "$BRANCH" --tags
echo "[post-commit] pushed $BRANCH + tags to $(git remote get-url origin)"
