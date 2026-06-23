#!/bin/bash
# Start the local review console now.
# Usage: ./start-console.sh <media-dir> [port] [video-dir]
# Env:   AUTOBOARD_APP=<path to app.py>   (default: installed skill)
set -e
MEDIA="${1:?media-dir required}"; PORT="${2:-8765}"; VDIR="${3:-}"
APP="${AUTOBOARD_APP:-$HOME/.claude/skills/mcp-review-console/app.py}"
[ -f "$APP" ] || APP="$(cd "$(dirname "$0")/../skills/mcp-review-console" && pwd)/app.py"
lsof -ti tcp:"$PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true
ARGS=(--mode image --media-dir "$MEDIA" --port "$PORT" --no-open)
[ -n "$VDIR" ] && ARGS+=(--video-dir "$VDIR")
nohup python3 "$APP" "${ARGS[@]}" >/tmp/autoboard-console.log 2>&1 &
sleep 1
open "http://localhost:$PORT/" 2>/dev/null || true
echo "Console: http://localhost:$PORT/   (app=$APP, media=$MEDIA)"
