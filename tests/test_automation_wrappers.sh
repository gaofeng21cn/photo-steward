#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/fake-python" <<'PY'
#!/bin/zsh
set -euo pipefail

if [[ "${1:-}" == "-c" ]]; then
  exec python3 "$@"
fi

if [[ "${1:-}" == "-m" && "${2:-}" == "tools.icloud_photo_sync.cli" ]]; then
  if [[ -n "${PHOTO_STEWARD_TEST_CLI_LOG:-}" ]]; then
    print -r -- "${@:3}" >> "$PHOTO_STEWARD_TEST_CLI_LOG"
  fi
  case "${3:-}" in
    config)
      if [[ "${4:-}" == validate ]]; then
        print -r -- "{\"runtime_state_dir\":\"${PHOTO_STEWARD_TEST_STATE:-$HOME/Library/Application Support/Photo Steward/state}\"}"
      fi
      exit 0
      ;;
    preflight|plan-job|todo-plan-job)
      exit 0
      ;;
    status)
      print -r -- '{"jobs":{"plan":{"summary":{"mirror_count":1,"delete_count":0,"unresolved_count":0}},"todo_plan":{"summary":{"copy_count":1,"move_count":0,"unresolved_count":0}}}}'
      exit 0
      ;;
  esac
fi

exit 0
PY
chmod +x "$TMP_DIR/fake-python"

for wrapper in run_plan.sh run_todo_plan.sh; do
  (
    export PYTHON_BIN="$TMP_DIR/fake-python"
    export PHOTO_STEWARD_CONFIG="$TMP_DIR/config.toml"
    export NAS_PREFLIGHT_ATTEMPTS=1
    export NAS_PREFLIGHT_INTERVAL_SECONDS=0
    "$ROOT_DIR/scripts/$wrapper"
  )
done

(
  export PYTHON_BIN="$TMP_DIR/fake-python"
  export PHOTO_STEWARD_CONFIG="$TMP_DIR/config.toml"
  export NAS_PREFLIGHT_ATTEMPTS=1
  export NAS_PREFLIGHT_INTERVAL_SECONDS=0
  export PHOTO_STEWARD_TEST_CLI_LOG="$TMP_DIR/cli.log"
  "$ROOT_DIR/scripts/run_deleted_pool_retention.sh"
)
rg -Fq 'prune-deleted-pool --dry-run' "$TMP_DIR/cli.log"

MAINTENANCE_RUNTIME="$TMP_DIR/maintenance-runtime"
mkdir -p "$MAINTENANCE_RUNTIME/scripts"
cp "$ROOT_DIR/scripts/run_nas_maintenance.sh" "$MAINTENANCE_RUNTIME/scripts/"
cat > "$MAINTENANCE_RUNTIME/scripts/run_onedrive_backup.sh" <<'SH'
#!/bin/zsh
print onedrive >> "$PHOTO_STEWARD_TEST_ORDER"
SH
cat > "$MAINTENANCE_RUNTIME/scripts/run_deleted_pool_retention.sh" <<'SH'
#!/bin/zsh
print retention >> "$PHOTO_STEWARD_TEST_ORDER"
SH
chmod +x "$MAINTENANCE_RUNTIME/scripts/"*.sh
PHOTO_STEWARD_RUNTIME_ROOT="$MAINTENANCE_RUNTIME" \
PHOTO_STEWARD_INCLUDE_ONEDRIVE=true \
PHOTO_STEWARD_TEST_ORDER="$TMP_DIR/maintenance-order" \
  "$MAINTENANCE_RUNTIME/scripts/run_nas_maintenance.sh"
[[ "$(<"$TMP_DIR/maintenance-order")" == $'onedrive\nretention' ]]

FAKE_RUNTIME="$TMP_DIR/runtime"
mkdir -p "$FAKE_RUNTIME/scripts/lib" "$TMP_DIR/state"
cp "$ROOT_DIR/scripts/run_weekly_orchestrator.sh" "$FAKE_RUNTIME/scripts/"
cp "$ROOT_DIR/scripts/lib/automation_common.sh" "$FAKE_RUNTIME/scripts/lib/"
cat > "$FAKE_RUNTIME/scripts/run_plan.sh" <<'SH'
#!/bin/zsh
print plan >> "$PHOTO_STEWARD_TEST_ORDER"
exit 7
SH
cat > "$FAKE_RUNTIME/scripts/run_todo_plan.sh" <<'SH'
#!/bin/zsh
print todo >> "$PHOTO_STEWARD_TEST_ORDER"
exit 0
SH
chmod +x "$FAKE_RUNTIME/scripts/"*.sh

set +e
PHOTO_STEWARD_RUNTIME_ROOT="$FAKE_RUNTIME" \
PYTHON_BIN="$TMP_DIR/fake-python" \
PHOTO_STEWARD_CONFIG="$TMP_DIR/config.toml" \
PHOTO_STEWARD_INCLUDE_TODO=true \
PHOTO_STEWARD_TEST_ORDER="$TMP_DIR/order" \
PHOTO_STEWARD_TEST_STATE="$TMP_DIR/state" \
  "$FAKE_RUNTIME/scripts/run_weekly_orchestrator.sh" >/dev/null
weekly_exit=$?
set -e
[[ "$weekly_exit" == 7 ]]
[[ "$(<"$TMP_DIR/order")" == $'plan\ntodo' ]]

cat > "$FAKE_RUNTIME/scripts/run_plan.sh" <<'SH'
#!/bin/zsh
exit 0
SH
cat > "$FAKE_RUNTIME/scripts/run_todo_plan.sh" <<'SH'
#!/bin/zsh
exit 0
SH
cat > "$TMP_DIR/fake-python-business" <<'PY'
#!/bin/zsh
set -euo pipefail

if [[ "${1:-}" == "-c" ]]; then
  exec python3 "$@"
fi
if [[ "${1:-}" == "-m" && "${2:-}" == "tools.icloud_photo_sync.cli" ]]; then
  case "${3:-}" in
    config)
      print -r -- "{\"runtime_state_dir\":\"$PHOTO_STEWARD_TEST_STATE\"}"
      ;;
    status)
      if [[ "${5:-}" == todo ]]; then
        print -r -- '{"jobs":{"todo_plan":{"status":"success","summary":{"status":"blocked","unresolved_count":3}}}}'
      else
        print -r -- '{"jobs":{"plan":{"status":"success","summary":{"mirror_count":2,"delete_count":0,"unresolved_count":0}}}}'
      fi
      ;;
  esac
  exit 0
fi
exit 0
PY
chmod +x "$TMP_DIR/fake-python-business"

PHOTO_STEWARD_RUNTIME_ROOT="$FAKE_RUNTIME" \
PYTHON_BIN="$TMP_DIR/fake-python-business" \
PHOTO_STEWARD_CONFIG="$TMP_DIR/config.toml" \
PHOTO_STEWARD_INCLUDE_TODO=true \
PHOTO_STEWARD_TEST_STATE="$TMP_DIR/state" \
  "$FAKE_RUNTIME/scripts/run_weekly_orchestrator.sh" >/dev/null
"$TMP_DIR/fake-python-business" - "$TMP_DIR/state/scheduler/latest_weekly.json" <<'PY'
import json
from pathlib import Path
import sys

receipt = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert receipt["status"] == "needs_attention"
assert receipt["jobs"]["plan"]["business_status"] == "review_ready"
assert receipt["jobs"]["todo"]["business_status"] == "blocked"
PY

print "automation_wrappers: status summarizers and non-fail-fast weekly execution are valid"
