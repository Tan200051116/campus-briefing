#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="/opt/campus-briefing"
lock_file="$repo_dir/server/data/official-git-sync.lock"

mkdir -p "$(dirname "$lock_file")"
exec 9>"$lock_file"
if ! flock -n 9; then
  echo "Another official sync is still running; skip this cycle."
  exit 0
fi

hour=$(TZ=Asia/Shanghai date +%H)
if (( 10#$hour < 8 || 10#$hour >= 22 )); then
  echo "Outside 08:00-22:00 Beijing time; skip."
  exit 0
fi

cd "$repo_dir"
git pull --rebase --autostash origin main

server/.venv/bin/python server/fetch_official.py

if git diff --quiet -- official-events.json; then
  echo "No briefing changes."
  exit 0
fi

git add official-events.json
git \
  -c user.name="campus-briefing-vps" \
  -c user.email="campus-briefing-vps@users.noreply.github.com" \
  commit -m "data: update official briefings"

# If another legitimate repository update landed during the scrape, rebase once
# and push the data commit on top of it. A failure is safe: the next timer run retries.
git pull --rebase origin main
git push origin HEAD:main
