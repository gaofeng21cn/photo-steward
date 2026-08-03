#!/bin/zsh
set -u
set -o pipefail

ROOT_DIR="${PHOTO_STEWARD_RUNTIME_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT_DIR"

overall_exit=0
typeset -a failures

if [[ "${PHOTO_STEWARD_INCLUDE_ONEDRIVE:-false}" == true ]]; then
  if "$ROOT_DIR/scripts/run_onedrive_backup.sh"; then
    :
  else
    exit_code=$?
    failures+=("onedrive=${exit_code}")
    overall_exit=$exit_code
  fi
fi

if "$ROOT_DIR/scripts/run_deleted_pool_retention.sh"; then
  :
else
  exit_code=$?
  failures+=("retention_audit=${exit_code}")
  (( overall_exit == 0 )) && overall_exit=$exit_code
fi

if (( overall_exit != 0 )); then
  print -u2 -r -- "NAS maintenance incomplete: ${(j:, :)failures}"
fi
exit "$overall_exit"
