#!/bin/zsh

notify_sync() {
  /usr/bin/osascript -e "display notification \"$1\" with title \"Photo Steward\"" >/dev/null 2>&1 || true
}

resolve_photo_config() {
  if [[ -z "${PHOTO_STEWARD_CONFIG:-}" ]]; then
    if [[ -n "${ICLOUD_PHOTO_SYNC_CONFIG:-}" ]]; then
      PHOTO_STEWARD_CONFIG="$ICLOUD_PHOTO_SYNC_CONFIG"
    else
      PHOTO_STEWARD_CONFIG="$("$PYTHON_BIN" -m tools.icloud_photo_sync.cli config path)" || return 2
    fi
  fi
  export PHOTO_STEWARD_CONFIG
}

photo_cli() {
  "$PYTHON_BIN" -m tools.icloud_photo_sync.cli "$@"
}

NAS_PREFLIGHT_ATTEMPTS="${NAS_PREFLIGHT_ATTEMPTS:-3}"
NAS_PREFLIGHT_INTERVAL_SECONDS="${NAS_PREFLIGHT_INTERVAL_SECONDS:-10}"
NAS_PREFLIGHT_TIMEOUT_SECONDS="${NAS_PREFLIGHT_TIMEOUT_SECONDS:-10}"

if [[ -z "${PHOTO_STEWARD_RUNTIME_ROOT:-}" && -x "$ROOT_DIR/bin/python3" ]]; then
  PHOTO_STEWARD_RUNTIME_ROOT="$ROOT_DIR"
  export PHOTO_STEWARD_RUNTIME_ROOT
fi

resolve_python() {
  local candidate
  local -a candidates
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    candidates+=("$PYTHON_BIN")
  fi
  candidates+=(
    "${PHOTO_STEWARD_RUNTIME_ROOT:-}/bin/python3"
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
      if [[ -n "${PHOTO_STEWARD_RUNTIME_ROOT:-}" ]]; then
        export PYTHONPATH="$PHOTO_STEWARD_RUNTIME_ROOT/vendor:$PHOTO_STEWARD_RUNTIME_ROOT${PYTHONPATH:+:$PYTHONPATH}"
        export PHOTO_STEWARD_PHOTOS_BRIDGE="$PHOTO_STEWARD_RUNTIME_ROOT/bin/PhotoStewardPhotosBridge.app/Contents/MacOS/photos_bridge"
      fi
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
  local probe_dir
  local stderr_path
  probe_dir="$(mktemp -d "${TMPDIR:-/tmp}/icloud-photo-sync-preflight.XXXXXX")"
  while (( attempt <= NAS_PREFLIGHT_ATTEMPTS )); do
    output=""
    elapsed=0
    stderr_path="$probe_dir/attempt-${attempt}.stderr"
    photo_cli preflight >"$probe_dir/attempt-${attempt}.stdout" 2>"$stderr_path" &
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
      if wait "$child_pid"; then
        /bin/rm -rf "$probe_dir"
        return 0
      else
        output="exit code $?"
      fi
    fi
    if [[ -s "$stderr_path" ]]; then
      output="${output}; $(tail -1 "$stderr_path")"
    fi
    echo "NAS preflight attempt ${attempt}/${NAS_PREFLIGHT_ATTEMPTS} failed: ${output}" >&2
    if (( attempt < NAS_PREFLIGHT_ATTEMPTS )); then
      sleep "$NAS_PREFLIGHT_INTERVAL_SECONDS"
    fi
    attempt=$((attempt + 1))
  done

  /bin/rm -rf "$probe_dir"
  echo "NAS mount preflight failed after ${NAS_PREFLIGHT_ATTEMPTS} attempts" >&2
  return 1
}

record_job_failure() {
  local job_name="$1"
  local message="$2"
  local exit_code="$3"
  photo_cli record-failure \
    --job-name "$job_name" \
    --message "$message" \
    --exit-code "$exit_code"
}
