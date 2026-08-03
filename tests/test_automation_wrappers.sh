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

print "automation_wrappers: manual plan, ToDo plan, and retention audit wrappers are valid"
