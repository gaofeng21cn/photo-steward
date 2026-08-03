#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
[[ -x "$ROOT_DIR/scripts/install_launchd_agents.sh" ]]
installer_text="$(<"$ROOT_DIR/scripts/install_launchd_agents.sh")"
normalized_installer_text="$(print -r -- "$installer_text" | sed 's/^[[:space:]]*//')"

assert_mapping() {
  local label="$1"
  local wrapper="$2"
  local expected
  expected="$(printf 'write_plist \\\n"%s" \\\n"$ROOT_DIR/scripts/%s"' "$label" "$wrapper")"
  print -r -- "$normalized_installer_text" | rg -U -Fq -- "$expected"
}

assert_mapping '$WEEKLY_LABEL' "run_weekly_orchestrator.sh"
assert_mapping "com.photosteward.nas-maintenance.weekly" "run_nas_maintenance.sh"

[[ "$installer_text" != *"APP_EXECUTABLE"* ]]
[[ "$installer_text" != *"--run-job"* ]]
[[ "$installer_text" == *"PHOTO_STEWARD_CONFIG"* ]]
[[ "$installer_text" == *"EnvironmentVariables"* ]]
[[ "$installer_text" == *"plistlib.dump"* ]]
[[ "$installer_text" == *"plutil -lint"* ]]
[[ "$installer_text" == *"SCHEDULE_WEEKDAY=0"* ]]
[[ "$installer_text" == *'"Weekday": int(weekday)'* ]]
[[ "$installer_text" == *'Library/Logs/Photo Steward'* ]]
[[ "$installer_text" != *'nasMountURL'* ]]
[[ "$installer_text" != *'tmp/automation'* ]]
[[ "$installer_text" == *'*.icloud-photo-sync.*.plist(N)'* ]]
[[ "$installer_text" == *'PHOTO_STEWARD_INCLUDE_TODO'* ]]
[[ "$installer_text" == *'PHOTO_STEWARD_INCLUDE_ONEDRIVE'* ]]
[[ "$installer_text" == *'nas_external_receipt_is_valid'* ]]
[[ "$installer_text" != *'DSM Task Scheduler owns NAS maintenance'* ]]

for retired_label in \
  com.photosteward.plan.daily \
  com.photosteward.todo.daily \
  com.photosteward.deleted-pool.daily \
  com.photosteward.onedrive.daily; do
  [[ "$installer_text" == *"\"$retired_label\""* ]]
done

app_source="$(<"$ROOT_DIR/app/PhotoCenterMenuBar/Sources/PhotoCenterMenuBar/main.swift")"
[[ "$app_source" != *"--run-job"* ]]
[[ "$app_source" != *"runScheduledJobIfRequested"* ]]

print "launchd_job: weekly orchestrator and guarded NAS fallback share one private config contract"
