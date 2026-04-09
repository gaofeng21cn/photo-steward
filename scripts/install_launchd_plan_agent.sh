#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$AGENT_DIR/com.gaofeng.icloud-photo-sync.plan.daily.plist"
UID_VALUE="$(id -u)"

mkdir -p "$AGENT_DIR" "$ROOT_DIR/tmp/automation"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.gaofeng.icloud-photo-sync.plan.daily</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT_DIR/scripts/run_plan.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>RunAtLoad</key>
  <false/>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>3</integer>
    <key>Minute</key>
    <integer>15</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$ROOT_DIR/tmp/automation/plan.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT_DIR/tmp/automation/plan.stderr.log</string>
</dict>
</plist>
PLIST

/bin/chmod 644 "$PLIST_PATH"
/bin/chmod +x "$ROOT_DIR/scripts/run_plan.sh" "$ROOT_DIR/scripts/run_apply_latest.sh" "$ROOT_DIR/scripts/install_launchd_plan_agent.sh"

/bin/launchctl bootout "gui/$UID_VALUE" "$PLIST_PATH" >/dev/null 2>&1 || true
/bin/launchctl bootstrap "gui/$UID_VALUE" "$PLIST_PATH"
/bin/launchctl enable "gui/$UID_VALUE/com.gaofeng.icloud-photo-sync.plan.daily"

echo "$PLIST_PATH"

