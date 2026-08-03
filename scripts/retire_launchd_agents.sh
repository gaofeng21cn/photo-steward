#!/bin/zsh
set -euo pipefail

AGENT_DIR="${PHOTO_STEWARD_LAUNCH_AGENT_DIR:-$HOME/Library/LaunchAgents}"
LAUNCHCTL="${PHOTO_STEWARD_LAUNCHCTL:-/bin/launchctl}"
UID_VALUE="${PHOTO_STEWARD_UID:-$(id -u)}"

typeset -a LABELS
LABELS=(
  "com.photosteward.weekly"
  "com.photosteward.nas-maintenance.weekly"
  "com.photosteward.plan.daily"
  "com.photosteward.todo.daily"
  "com.photosteward.deleted-pool.daily"
  "com.photosteward.onedrive.daily"
)

for label in "${LABELS[@]}"; do
  "$LAUNCHCTL" bootout "gui/$UID_VALUE/$label" >/dev/null 2>&1 || true
  /bin/rm -f "$AGENT_DIR/$label.plist"
done

for legacy_plist in "$AGENT_DIR"/*.icloud-photo-sync.*.plist(N); do
  legacy_label="$(/usr/libexec/PlistBuddy -c 'Print :Label' "$legacy_plist" 2>/dev/null || true)"
  if [[ -n "$legacy_label" ]]; then
    "$LAUNCHCTL" bootout "gui/$UID_VALUE/$legacy_label" >/dev/null 2>&1 || true
  fi
  /bin/rm -f "$legacy_plist"
done

print "Photo Steward background schedules retired"
