#!/usr/bin/env bash
#
# Installs git hooks for this repo. Run once after a fresh clone.
# Currently: a post-commit hook that mirrors the repo to the OneDrive backup and pushes to
# GitHub - two independent, automatic backups after every commit.
#
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$REPO/.git/hooks/post-commit"

cat > "$HOOK" <<'EOF'
#!/usr/bin/env bash
# Auto-backup after every commit: OneDrive mirror, then push to GitHub. Neither blocks the
# commit - a failure in either is reported but ignored, so a network hiccup or a offline
# session in the yard never gets in the way of committing.
REPO="$(git rev-parse --show-toplevel)"
"$REPO/scripts/backup-to-onedrive.sh" || echo "[post-commit] OneDrive backup failed (non-fatal)"
"$REPO/scripts/push-to-github.sh"     || echo "[post-commit] GitHub push failed (non-fatal)"
EOF

chmod +x "$HOOK"
echo "Installed post-commit hook: $HOOK"
