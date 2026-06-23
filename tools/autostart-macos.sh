#!/bin/bash
# Auto-start the console at login (macOS launchd).
#   ./autostart-macos.sh install <media-dir> [port] [video-dir]
#   ./autostart-macos.sh uninstall
# Env: AUTOBOARD_APP=<path to app.py> (default: installed skill)
set -e
LABEL="com.autoboard.review-console"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
case "${1:-}" in
 install)
  MEDIA="${2:?media-dir required}"; PORT="${3:-8765}"; VDIR="${4:-}"
  APP="${AUTOBOARD_APP:-$HOME/.claude/skills/mcp-review-console/app.py}"
  PY="$(command -v python3)"
  mkdir -p "$HOME/Library/LaunchAgents"
  VARG=""; [ -n "$VDIR" ] && VARG="<string>--video-dir</string><string>$VDIR</string>"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
 <key>Label</key><string>$LABEL</string>
 <key>ProgramArguments</key><array>
   <string>$PY</string><string>$APP</string>
   <string>--mode</string><string>image</string>
   <string>--media-dir</string><string>$MEDIA</string>
   <string>--port</string><string>$PORT</string>
   $VARG
   <string>--no-open</string>
 </array>
 <key>RunAtLoad</key><true/>
 <key>KeepAlive</key><true/>
 <key>StandardOutPath</key><string>/tmp/autoboard-console.log</string>
 <key>StandardErrorPath</key><string>/tmp/autoboard-console.err</string>
</dict></plist>
EOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "Installed: console auto-starts at login on http://localhost:$PORT/ (media=$MEDIA)"
  ;;
 uninstall)
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"; echo "Uninstalled auto-start."
  ;;
 *) echo "Usage: $0 install <media-dir> [port] [video-dir]  |  $0 uninstall"; exit 1;;
esac
