#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/fake-python" <<'PY'
#!/bin/zsh
set -euo pipefail
if [[ "${1:-}" == "-c" ]]; then
  exit 0
fi
if [[ "${1:-}" == "-m" && "${3:-}" == "config" && "${4:-}" == "path" ]]; then
  print -r -- "${FAKE_CONFIG_PATH:?}"
  exit 0
fi
if [[ "${1:-}" == "-m" && "${3:-}" == "preflight" ]]; then
  [[ "${PHOTO_STEWARD_CONFIG:-}" == "${FAKE_CONFIG_PATH:?}" ]] || exit 9
  if [[ "${FAKE_TIMEOUT:-false}" == true ]]; then
    sleep 3
    exit 0
  fi
  count_file="${FAKE_COUNT_FILE:?}"
  count=0
  [[ -f "$count_file" ]] && count="$(<"$count_file")"
  count=$((count + 1))
  print -r -- "$count" > "$count_file"
  (( count >= 2 )) && exit 0
  exit 1
fi
exit 0
PY
chmod +x "$TMP_DIR/fake-python"

(
  export PYTHON_BIN="$TMP_DIR/fake-python"
  export FAKE_COUNT_FILE="$TMP_DIR/count"
  export FAKE_CONFIG_PATH="$TMP_DIR/config.toml"
  export NAS_PREFLIGHT_ATTEMPTS=3
  export NAS_PREFLIGHT_INTERVAL_SECONDS=0
  source "$ROOT_DIR/scripts/lib/automation_common.sh"
  resolve_python
  resolve_photo_config
  wait_for_nas_mount
)

[[ "$(<"$TMP_DIR/count")" == "2" ]]
print "automation_common: wait_for_nas_mount retries and succeeds"

if (
  export PYTHON_BIN="$TMP_DIR/fake-python"
  export FAKE_TIMEOUT=true
  export FAKE_CONFIG_PATH="$TMP_DIR/config.toml"
  export NAS_PREFLIGHT_ATTEMPTS=1
  export NAS_PREFLIGHT_INTERVAL_SECONDS=0
  export NAS_PREFLIGHT_TIMEOUT_SECONDS=1
  source "$ROOT_DIR/scripts/lib/automation_common.sh"
  resolve_python
  resolve_photo_config
  wait_for_nas_mount
); then
  print -u2 "expected preflight timeout to fail"
  exit 1
fi
print "automation_common: preflight timeout fails closed"
