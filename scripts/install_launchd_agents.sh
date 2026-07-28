#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENT_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/Photo Steward"
UID_VALUE="$(id -u)"
INCLUDE_TODO=false
PHOTO_ONLY=false
CORE_ONLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --include-todo)
      INCLUDE_TODO=true
      ;;
    --photo-only)
      PHOTO_ONLY=true
      ;;
    --core-only)
      CORE_ONLY=true
      ;;
    *)
      echo "usage: $0 [--include-todo] [--photo-only] [--core-only]" >&2
      exit 2
      ;;
  esac
  shift
done

ROOT_DIR="${PHOTO_STEWARD_RUNTIME_ROOT:-$ROOT_DIR}"
source "$ROOT_DIR/scripts/lib/automation_common.sh"
cd "$ROOT_DIR"

if ! resolve_python; then
  exit 127
fi
if ! resolve_photo_config; then
  echo "Photo Steward configuration unavailable" >&2
  exit 2
fi
photo_cli config validate >/dev/null
photo_cli config activate >/dev/null

mkdir -p "$AGENT_DIR" "$LOG_DIR"
if [[ -x "$ROOT_DIR/scripts/install_menu_bar_app.sh" ]]; then
  "$ROOT_DIR/scripts/install_menu_bar_app.sh" >/dev/null
fi

# Migrate the previous private label family without embedding its owner name.
for legacy_plist in "$AGENT_DIR"/*.icloud-photo-sync.*.plist(N); do
  legacy_label="$(/usr/libexec/PlistBuddy -c 'Print :Label' "$legacy_plist" 2>/dev/null || true)"
  if [[ -n "$legacy_label" ]]; then
    /bin/launchctl bootout "gui/$UID_VALUE/$legacy_label" >/dev/null 2>&1 || true
  fi
  /bin/rm -f "$legacy_plist"
done

write_plist() {
  local label="$1"
  local executable="$2"
  local hour="$3"
  local minute="$4"
  local stdout_path="$5"
  local stderr_path="$6"
  local plist_path="$AGENT_DIR/$label.plist"

  "$PYTHON_BIN" - \
    "$plist_path" "$label" "$executable" "$ROOT_DIR" "$hour" "$minute" \
    "$stdout_path" "$stderr_path" "$PHOTO_STEWARD_CONFIG" <<'PY'
from pathlib import Path
import plistlib
import sys

(
    plist_path,
    label,
    executable,
    working_directory,
    hour,
    minute,
    stdout_path,
    stderr_path,
    config_path,
) = sys.argv[1:]

payload = {
    "Label": label,
    "ProgramArguments": [executable],
    "WorkingDirectory": working_directory,
    "RunAtLoad": False,
    "StartCalendarInterval": {"Hour": int(hour), "Minute": int(minute)},
    "EnvironmentVariables": {"PHOTO_STEWARD_CONFIG": config_path},
    "StandardOutPath": stdout_path,
    "StandardErrorPath": stderr_path,
}
with Path(plist_path).open("wb") as handle:
    plistlib.dump(payload, handle, sort_keys=False)
PY

  /bin/chmod 644 "$plist_path"
  /usr/bin/plutil -lint "$plist_path" >/dev/null
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
  "$ROOT_DIR/scripts/install_launchd_todo_agent.sh" \
  "$ROOT_DIR/scripts/install_launchd_agents.sh"

TODO_LABEL="com.photosteward.todo.daily"
if [[ "$CORE_ONLY" == false ]]; then
  /bin/launchctl bootout "gui/$UID_VALUE/$TODO_LABEL" >/dev/null 2>&1 || true
  /bin/rm -f "$AGENT_DIR/$TODO_LABEL.plist"
fi
if [[ "$PHOTO_ONLY" == true && "$CORE_ONLY" == false ]]; then
  /bin/launchctl bootout "gui/$UID_VALUE/com.photosteward.onedrive.daily" >/dev/null 2>&1 || true
  /bin/rm -f "$AGENT_DIR/com.photosteward.onedrive.daily.plist"
fi

write_plist \
  "com.photosteward.plan.daily" \
  "$ROOT_DIR/scripts/run_plan.sh" \
  "3" \
  "15" \
  "$LOG_DIR/plan.stdout.log" \
  "$LOG_DIR/plan.stderr.log"

write_plist \
  "com.photosteward.deleted-pool.daily" \
  "$ROOT_DIR/scripts/run_deleted_pool_retention.sh" \
  "4" \
  "0" \
  "$LOG_DIR/deleted-pool.stdout.log" \
  "$LOG_DIR/deleted-pool.stderr.log"

if [[ "$PHOTO_ONLY" == false && "$CORE_ONLY" == false ]]; then
  write_plist \
    "com.photosteward.onedrive.daily" \
    "$ROOT_DIR/scripts/run_onedrive_backup.sh" \
    "4" \
    "15" \
    "$LOG_DIR/onedrive.stdout.log" \
    "$LOG_DIR/onedrive.stderr.log"
fi

if [[ "$INCLUDE_TODO" == true && "$PHOTO_ONLY" == false && "$CORE_ONLY" == false ]]; then
  /bin/chmod +x "$ROOT_DIR/scripts/run_todo_plan.sh"
  write_plist \
    "$TODO_LABEL" \
    "$ROOT_DIR/scripts/run_todo_plan.sh" \
    "4" \
    "30" \
    "$LOG_DIR/todo.stdout.log" \
    "$LOG_DIR/todo.stderr.log"
fi

printf '%s\n' \
  "$AGENT_DIR/com.photosteward.plan.daily.plist" \
  "$AGENT_DIR/com.photosteward.deleted-pool.daily.plist"
if [[ "$PHOTO_ONLY" == false && "$CORE_ONLY" == false ]]; then
  printf '%s\n' "$AGENT_DIR/com.photosteward.onedrive.daily.plist"
fi
if [[ "$INCLUDE_TODO" == true && "$PHOTO_ONLY" == false && "$CORE_ONLY" == false ]]; then
  printf '%s\n' "$AGENT_DIR/$TODO_LABEL.plist"
fi
