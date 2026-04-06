#!/usr/bin/env bash
# enable-github-pages.sh
# Enables GitHub Pages for this repo (serves from main branch / root folder).
# Run once from your terminal:
#     bash enable-github-pages.sh
#
# Requires: GitHub CLI (gh) — https://cli.github.com
#           Run 'gh auth login' first if not already authenticated.

set -e

REPO="aruijter72/Archimate-engine"
LIVE_URL="https://aruijter72.github.io/Archimate-engine/"

echo ""
echo "Enabling GitHub Pages for: $REPO"
echo ""

# Try to enable Pages via the API (requires 'pages' scope in gh auth)
gh api "repos/$REPO/pages" \
  --method POST \
  -f "source[branch]=main" \
  -f "source[path]=/" \
  --silent && echo "GitHub Pages enabled!" \
           || echo "Note: Pages may already be enabled, or requires manual activation in Settings."

echo ""
echo "Your live URL will be:  $LIVE_URL"
echo ""
echo "Pages usually goes live within 1-2 minutes of the first push."
echo "Future pushes (via autopush.sh) will automatically update the live site."
echo ""
echo "If this script fails, enable Pages manually:"
echo "  1. Open https://github.com/$REPO/settings/pages"
echo "  2. Under 'Source', select: Deploy from a branch"
echo "  3. Branch: main   /   Folder: / (root)"
echo "  4. Click Save"
echo ""
