#!/usr/bin/env bash
#
# Installs git hooks for this repo. Run once after a fresh clone.
# Currently: a post-commit hook that mirrors the repo to the OneDrive backup.
#
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO/.git/hooks/post-commit"

cat > "$HOOK" <<'EOF'
#!/usr/bin/env bash
# Auto-mirror the repo to the OneDrive backup after every commit.
# Never blocks the commit: failures are reported but ignored.
REPO="$(git rev-parse --show-toplevel)"
"$REPO/scripts/backup-to-onedrive.sh" || echo "[post-commit] backup failed (non-fatal)"
EOF

chmod +x "$HOOK"
echo "Installed post-commit hook: $HOOK"
