#!/bin/zsh

notify_sync() {
  /usr/bin/osascript -e "display notification \"$1\" with title \"icloud-photo-sync\"" >/dev/null 2>&1 || true
}

NAS_PREFLIGHT_ATTEMPTS="${NAS_PREFLIGHT_ATTEMPTS:-6}"
NAS_PREFLIGHT_INTERVAL_SECONDS="${NAS_PREFLIGHT_INTERVAL_SECONDS:-20}"
NAS_PREFLIGHT_TIMEOUT_SECONDS="${NAS_PREFLIGHT_TIMEOUT_SECONDS:-15}"

resolve_python() {
  local candidate
  local -a candidates
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    candidates+=("$PYTHON_BIN")
  fi
  candidates+=(
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"
    "$HOME/.py-global/bin/python3"
  )

  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]] && "$candidate" -c \
      'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
      >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      export PYTHON_BIN
      return 0
    fi
  done

  echo "working Python 3.10+ runtime not found" >&2
  return 127
}

wait_for_nas_mount() {
  local attempt=1
  local output
  local child_pid
  local elapsed
  while (( attempt <= NAS_PREFLIGHT_ATTEMPTS )); do
    output=""
    elapsed=0
    "$PYTHON_BIN" -m tools.icloud_photo_sync.cli preflight > >(cat) 2> >(cat >&2) &
    child_pid=$!
    while kill -0 "$child_pid" 2>/dev/null; do
      if (( elapsed >= NAS_PREFLIGHT_TIMEOUT_SECONDS )); then
        kill "$child_pid" 2>/dev/null || true
        wait "$child_pid" 2>/dev/null || true
        output="timed out after ${NAS_PREFLIGHT_TIMEOUT_SECONDS}s"
        break
      fi
      /bin/sleep 1
      elapsed=$((elapsed + 1))
    done
    if [[ -z "$output" ]]; then
      if wait "$child_pid" > >(cat) 2> >(cat >&2); then
        return 0
      else
        output="exit code $?"
      fi
    fi
    echo "NAS preflight attempt ${attempt}/${NAS_PREFLIGHT_ATTEMPTS} failed: ${output}" >&2
    if (( attempt < NAS_PREFLIGHT_ATTEMPTS )); then
      sleep "$NAS_PREFLIGHT_INTERVAL_SECONDS"
    fi
    attempt=$((attempt + 1))
  done

  echo "NAS mount preflight failed after ${NAS_PREFLIGHT_ATTEMPTS} attempts" >&2
  return 1
}
