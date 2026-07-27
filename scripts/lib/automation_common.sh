#!/bin/zsh

notify_sync() {
  /usr/bin/osascript -e "display notification \"$1\" with title \"icloud-photo-sync\"" >/dev/null 2>&1 || true
}

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
