#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENT_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/Photo Steward"
STATE_DIR="$HOME/Library/Application Support/Photo Steward"
NAS_EXTERNAL_MARKER="$STATE_DIR/nas-jobs-external"
UID_VALUE="$(id -u)"
INCLUDE_TODO=false
PHOTO_ONLY=false
CORE_ONLY=false
NAS_JOBS_EXTERNAL=false
NAS_JOBS_EXTERNAL_REQUESTED=false
SCHEDULE_WEEKDAY=0

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
    --nas-jobs-external)
      NAS_JOBS_EXTERNAL_REQUESTED=true
      ;;
    *)
      echo "usage: $0 [--include-todo] [--photo-only] [--core-only] [--nas-jobs-external]" >&2
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

mkdir -p "$AGENT_DIR" "$LOG_DIR" "$STATE_DIR"

nas_external_receipt_is_valid() {
  [[ -f "$NAS_EXTERNAL_MARKER" ]] || return 1
  "$PYTHON_BIN" - "$NAS_EXTERNAL_MARKER" <<'PY'
import json
from pathlib import Path
import sys

try:
    receipt = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)

cloud_sync = receipt.get("cloud_sync", {})
valid = (
    receipt.get("schema_version") == 1
    and receipt.get("status") == "verified"
    and receipt.get("scheduler") == "synology_dsm_task_scheduler"
    and receipt.get("scheduler_status") == "installed"
    and cloud_sync.get("direction") == "upload_only"
    and cloud_sync.get("delete_destination_on_source_delete") is False
)
raise SystemExit(0 if valid else 1)
PY
}

if nas_external_receipt_is_valid; then
  NAS_JOBS_EXTERNAL=true
elif [[ "$NAS_JOBS_EXTERNAL_REQUESTED" == true ]]; then
  echo "--nas-jobs-external requires a verified receipt at $NAS_EXTERNAL_MARKER" >&2
  exit 2
fi

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
    "$SCHEDULE_WEEKDAY" "$stdout_path" "$stderr_path" "$PHOTO_STEWARD_CONFIG" <<'PY'
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
    weekday,
    stdout_path,
    stderr_path,
    config_path,
) = sys.argv[1:]

payload = {
    "Label": label,
    "ProgramArguments": [executable],
    "WorkingDirectory": working_directory,
    "RunAtLoad": False,
    "StartCalendarInterval": {
        "Weekday": int(weekday),
        "Hour": int(hour),
        "Minute": int(minute),
    },
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
  "$ROOT_DIR/scripts/run_weekly_orchestrator.sh" \
  "$ROOT_DIR/scripts/run_nas_maintenance.sh" \
  "$ROOT_DIR/scripts/run_plan.sh" \
  "$ROOT_DIR/scripts/run_todo_plan.sh" \
  "$ROOT_DIR/scripts/run_apply_latest.sh" \
  "$ROOT_DIR/scripts/run_deleted_pool_retention.sh" \
  "$ROOT_DIR/scripts/run_onedrive_backup.sh" \
  "$ROOT_DIR/scripts/install_launchd_todo_agent.sh" \
  "$ROOT_DIR/scripts/install_launchd_agents.sh"

WEEKLY_LABEL="com.photosteward.weekly"
typeset -a RETIRED_LABELS
RETIRED_LABELS=(
  "com.photosteward.plan.daily"
  "com.photosteward.todo.daily"
  "com.photosteward.deleted-pool.daily"
  "com.photosteward.onedrive.daily"
)
for label in "${RETIRED_LABELS[@]}"; do
  /bin/launchctl bootout "gui/$UID_VALUE/$label" >/dev/null 2>&1 || true
  /bin/rm -f "$AGENT_DIR/$label.plist"
done

write_plist \
  "$WEEKLY_LABEL" \
  "$ROOT_DIR/scripts/run_weekly_orchestrator.sh" \
  "3" \
  "15" \
  "$LOG_DIR/weekly.stdout.log" \
  "$LOG_DIR/weekly.stderr.log"

if [[ "$INCLUDE_TODO" == true ]]; then
  /usr/libexec/PlistBuddy -c 'Add :EnvironmentVariables:PHOTO_STEWARD_INCLUDE_TODO string true' \
    "$AGENT_DIR/$WEEKLY_LABEL.plist"
  /usr/bin/plutil -lint "$AGENT_DIR/$WEEKLY_LABEL.plist" >/dev/null
  /bin/launchctl bootout "gui/$UID_VALUE" "$AGENT_DIR/$WEEKLY_LABEL.plist" >/dev/null 2>&1 || true
  /bin/launchctl bootstrap "gui/$UID_VALUE" "$AGENT_DIR/$WEEKLY_LABEL.plist"
fi

if [[ "$NAS_JOBS_EXTERNAL" == true ]]; then
  /bin/launchctl bootout "gui/$UID_VALUE/com.photosteward.nas-maintenance.weekly" >/dev/null 2>&1 || true
  /bin/rm -f "$AGENT_DIR/com.photosteward.nas-maintenance.weekly.plist"
elif [[ "$CORE_ONLY" == false ]]; then
  write_plist \
    "com.photosteward.nas-maintenance.weekly" \
    "$ROOT_DIR/scripts/run_nas_maintenance.sh" \
    "4" \
    "0" \
    "$LOG_DIR/nas-maintenance.stdout.log" \
    "$LOG_DIR/nas-maintenance.stderr.log"

  if [[ "$PHOTO_ONLY" == false ]]; then
    /usr/libexec/PlistBuddy -c 'Add :EnvironmentVariables:PHOTO_STEWARD_INCLUDE_ONEDRIVE string true' \
      "$AGENT_DIR/com.photosteward.nas-maintenance.weekly.plist"
    /usr/bin/plutil -lint "$AGENT_DIR/com.photosteward.nas-maintenance.weekly.plist" >/dev/null
    /bin/launchctl bootout "gui/$UID_VALUE" "$AGENT_DIR/com.photosteward.nas-maintenance.weekly.plist" >/dev/null 2>&1 || true
    /bin/launchctl bootstrap "gui/$UID_VALUE" "$AGENT_DIR/com.photosteward.nas-maintenance.weekly.plist"
  fi
fi

printf '%s\n' "$AGENT_DIR/$WEEKLY_LABEL.plist"
if [[ "$NAS_JOBS_EXTERNAL" == false && "$CORE_ONLY" == false ]]; then
  printf '%s\n' "$AGENT_DIR/com.photosteward.nas-maintenance.weekly.plist"
fi
