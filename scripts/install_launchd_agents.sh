#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENT_DIR="$HOME/Library/LaunchAgents"
UID_VALUE="$(id -u)"

mkdir -p "$AGENT_DIR" "$ROOT_DIR/tmp/automation"

write_plist() {
  local label="$1"
  local script_path="$2"
  local hour="$3"
  local minute="$4"
  local stdout_path="$5"
  local stderr_path="$6"
  local plist_path="$AGENT_DIR/$label.plist"

  cat > "$plist_path" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>$script_path</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>RunAtLoad</key>
  <false/>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>$hour</integer>
    <key>Minute</key>
    <integer>$minute</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$stdout_path</string>
  <key>StandardErrorPath</key>
  <string>$stderr_path</string>
</dict>
</plist>
PLIST

  /bin/chmod 644 "$plist_path"
  /bin/launchctl bootout "gui/$UID_VALUE" "$plist_path" >/dev/null 2>&1 || true
  /bin/launchctl bootstrap "gui/$UID_VALUE" "$plist_path"
  /bin/launchctl enable "gui/$UID_VALUE/$label"
}

/bin/chmod +x \
  "$ROOT_DIR/scripts/run_plan.sh" \
  "$ROOT_DIR/scripts/run_todo_plan.sh" \
  "$ROOT_DIR/scripts/run_apply_latest.sh" \
  "$ROOT_DIR/scripts/run_deleted_pool_retention.sh" \
  "$ROOT_DIR/scripts/run_onedrive_backup.sh" \
  "$ROOT_DIR/scripts/install_launchd_plan_agent.sh" \
  "$ROOT_DIR/scripts/install_launchd_agents.sh"

write_plist \
  "com.gaofeng.icloud-photo-sync.plan.daily" \
  "$ROOT_DIR/scripts/run_plan.sh" \
  "3" \
  "15" \
  "$ROOT_DIR/tmp/automation/plan.stdout.log" \
  "$ROOT_DIR/tmp/automation/plan.stderr.log"

write_plist \
  "com.gaofeng.icloud-photo-sync.deleted-pool.daily" \
  "$ROOT_DIR/scripts/run_deleted_pool_retention.sh" \
  "4" \
  "0" \
  "$ROOT_DIR/tmp/automation/deleted-pool.stdout.log" \
  "$ROOT_DIR/tmp/automation/deleted-pool.stderr.log"

write_plist \
  "com.gaofeng.icloud-photo-sync.onedrive.daily" \
  "$ROOT_DIR/scripts/run_onedrive_backup.sh" \
  "4" \
  "15" \
  "$ROOT_DIR/tmp/automation/onedrive.stdout.log" \
  "$ROOT_DIR/tmp/automation/onedrive.stderr.log"

write_plist \
  "com.gaofeng.icloud-photo-sync.todo.daily" \
  "$ROOT_DIR/scripts/run_todo_plan.sh" \
  "4" \
  "30" \
  "$ROOT_DIR/tmp/automation/todo.stdout.log" \
  "$ROOT_DIR/tmp/automation/todo.stderr.log"

printf '%s\n' \
  "$AGENT_DIR/com.gaofeng.icloud-photo-sync.plan.daily.plist" \
  "$AGENT_DIR/com.gaofeng.icloud-photo-sync.todo.daily.plist" \
  "$AGENT_DIR/com.gaofeng.icloud-photo-sync.deleted-pool.daily.plist" \
  "$AGENT_DIR/com.gaofeng.icloud-photo-sync.onedrive.daily.plist"
