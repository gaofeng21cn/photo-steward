#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
installer_text="$(<"$ROOT_DIR/scripts/install_launchd_agents.sh")"
normalized_installer_text="$(print -r -- "$installer_text" | sed 's/^[[:space:]]*//')"

assert_mapping() {
  local label="$1"
  local wrapper="$2"
  local expected
  expected="$(printf 'write_plist \\\n"%s" \\\n"$ROOT_DIR/scripts/%s"' "$label" "$wrapper")"
  print -r -- "$normalized_installer_text" | rg -U -Fq -- "$expected"
}

assert_mapping "com.gaofeng.icloud-photo-sync.plan.daily" "run_plan.sh"
assert_mapping "com.gaofeng.icloud-photo-sync.deleted-pool.daily" "run_deleted_pool_retention.sh"
assert_mapping "com.gaofeng.icloud-photo-sync.onedrive.daily" "run_onedrive_backup.sh"
assert_mapping '$TODO_LABEL' "run_todo_plan.sh"

[[ "$installer_text" != *"APP_EXECUTABLE"* ]]
[[ "$installer_text" != *"--run-job"* ]]

app_source="$(<"$ROOT_DIR/app/PhotoCenterMenuBar/Sources/PhotoCenterMenuBar/main.swift")"
[[ "$app_source" != *"--run-job"* ]]
[[ "$app_source" != *"runScheduledJobIfRequested"* ]]

print "launchd_job: scheduled jobs map directly to repository wrappers"
