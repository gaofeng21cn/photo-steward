#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

AGENT_DIR="$TMP_DIR/LaunchAgents"
mkdir -p "$AGENT_DIR"

cat > "$TMP_DIR/launchctl" <<'SH'
#!/bin/zsh
print -r -- "$*" >> "$PHOTO_STEWARD_TEST_LAUNCHCTL_LOG"
exit 3
SH
chmod +x "$TMP_DIR/launchctl"

labels=(
  com.photosteward.weekly
  com.photosteward.nas-maintenance.weekly
  com.photosteward.plan.daily
  com.photosteward.todo.daily
  com.photosteward.deleted-pool.daily
  com.photosteward.onedrive.daily
)
for label in "${labels[@]}"; do
  print '<plist/>' > "$AGENT_DIR/$label.plist"
done

legacy_plist="$AGENT_DIR/dev.example.icloud-photo-sync.plan.plist"
/usr/libexec/PlistBuddy -c 'Add :Label string dev.example.icloud-photo-sync.plan' "$legacy_plist"

PHOTO_STEWARD_LAUNCH_AGENT_DIR="$AGENT_DIR" \
PHOTO_STEWARD_LAUNCHCTL="$TMP_DIR/launchctl" \
PHOTO_STEWARD_UID=999 \
PHOTO_STEWARD_TEST_LAUNCHCTL_LOG="$TMP_DIR/launchctl.log" \
  "$ROOT_DIR/scripts/retire_launchd_agents.sh" >/dev/null

[[ -z "$(find "$AGENT_DIR" -name '*.plist' -print -quit)" ]]
for label in "${labels[@]}"; do
  rg -Fq "bootout gui/999/$label" "$TMP_DIR/launchctl.log"
done
rg -Fq 'bootout gui/999/dev.example.icloud-photo-sync.plan' "$TMP_DIR/launchctl.log"

runtime_source="$(<"$ROOT_DIR/app/PhotoCenterMenuBar/Sources/PhotoCenterMenuBar/Services/PhotoStewardRuntime.swift")"
setup_source="$(<"$ROOT_DIR/app/PhotoCenterMenuBar/Sources/PhotoCenterMenuBar/Views/SetupView.swift")"
configuration_source="$(<"$ROOT_DIR/app/PhotoCenterMenuBar/Sources/PhotoCenterMenuBar/Views/ConfigurationView.swift")"

[[ "$runtime_source" == *"retire_launchd_agents.sh"* ]]
[[ "$runtime_source" != *"install_launchd_agents.sh"* ]]
[[ "$runtime_source" != *"agentsUseRuntime"* ]]
[[ "$setup_source" != *"installAgents"* ]]
[[ "$configuration_source" != *"installAgents"* ]]

for retired_script in \
  install_launchd_agents.sh \
  install_launchd_plan_agent.sh \
  install_launchd_todo_agent.sh \
  run_weekly_orchestrator.sh \
  run_nas_maintenance.sh; do
  [[ ! -e "$ROOT_DIR/scripts/$retired_script" ]]
done

print "launchd_job: legacy Photo Steward schedules are retired and cannot be reinstalled by the App"
