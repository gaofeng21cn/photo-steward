#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/Users/gaofeng/.py-global/bin/python3}"

notify() {
  /usr/bin/osascript -e "display notification \"$1\" with title \"icloud-photo-sync\"" >/dev/null 2>&1 || true
}

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "python runtime missing: $PYTHON_BIN" >&2
  exit 127
fi

mkdir -p "$ROOT_DIR/tmp/automation"
cd "$ROOT_DIR"

"$PYTHON_BIN" -m tools.icloud_photo_sync.cli backup-onedrive "$@"
exit_code=$?

if [[ $exit_code -ne 0 ]]; then
  notify "OneDrive backup failed"
fi

exit $exit_code

