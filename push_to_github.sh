#!/bin/bash
# Push cs-daily-manager to GitHub (marquant/cs-daily-manager)
set -e

REPO_NAME="cs-daily-manager"
REMOTE_URL="https://github.com/MarquantMa/cs-daily-manager.git"

GIT_CMD="/Library/Developer/CommandLineTools/usr/bin/git"
if [ ! -x "$GIT_CMD" ]; then
    GIT_CMD="git"
fi

echo "=== Pushing $REPO_NAME to GitHub ==="

# Check gh auth status
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    echo "GitHub CLI is authenticated. Ensuring remote repository exists..."
    gh repo create "MarquantMa/$REPO_NAME" --public --source=. --remote=origin --push || true
    echo "Pushing latest main branch..."
    $GIT_CMD push -u origin main
    echo "Successfully pushed $REPO_NAME to GitHub!"
    exit 0
fi

echo "GitHub CLI (gh) is not authenticated or not logged in."
echo "Attempting standard git push to $REMOTE_URL..."
$GIT_CMD push -u origin main || {
    echo ""
    echo "Push failed. Please authenticate GitHub:"
    echo "  1) Run: gh auth login"
    echo "  2) Or configure SSH / personal access token for git"
    echo "Then re-run this script: ./push_to_github.sh"
    exit 1
}
