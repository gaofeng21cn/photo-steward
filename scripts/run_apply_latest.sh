#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/automation_common.sh"
cd "$ROOT_DIR"

if ! resolve_python; then
  notify_sync "Python runtime unavailable"
  exit 127
fi
if ! resolve_photo_config; then
  notify_sync "Photo Steward configuration unavailable"
  exit 2
fi

if [[ "${1:-}" == "--plan-dir" ]]; then
  shift
  if [[ $# -lt 1 ]]; then
    echo "missing value for --plan-dir" >&2
    exit 2
  fi
  photo_cli apply-job --plan-dir "$1"
  exit $?
fi

echo "usage: $0 --plan-dir <plan_dir>" >&2
exit 2
