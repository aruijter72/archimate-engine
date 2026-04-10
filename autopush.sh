#!/bin/zsh
# autopush.sh — auto-commit and push changes in Architise
# Called by launchd WatchPaths when files change in this folder

cd "$(dirname "$0")"

# Nothing to do if working tree is clean
git diff --quiet && git diff --staged --quiet && [ -z "$(git ls-files --others --exclude-standard)" ] && exit 0

git add -A
git diff --staged --quiet && exit 0   # staged nothing (e.g. only .DS_Store)

git commit -m "autopush: $(date '+%Y-%m-%d %H:%M:%S')"
git push origin main >> "$(dirname "$0")/autopush.log" 2>&1
