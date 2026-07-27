#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_EXECUTABLE="$ROOT_DIR/app/PhotoCenterMenuBar/.build/release/PhotoCenterMenuBar"

swift build --package-path "$ROOT_DIR/app/PhotoCenterMenuBar" -c release >/dev/null

set +e
"$APP_EXECUTABLE" --run-job unknown >/dev/null 2>&1
exit_code=$?
set -e

[[ "$exit_code" == "64" ]]
print "launchd_job: signed app runner rejects unknown jobs with EX_USAGE"
