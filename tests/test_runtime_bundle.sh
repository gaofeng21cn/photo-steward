#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/tmp/test-runtime-bundle"

"$ROOT_DIR/scripts/stage_runtime.sh" "$RUNTIME_DIR" >/dev/null
[[ -x "$RUNTIME_DIR/bin/python3" ]]
[[ -x "$RUNTIME_DIR/bin/photos_bridge" ]]
[[ -x "$RUNTIME_DIR/bin/PhotoStewardPhotosBridge.app/Contents/MacOS/photos_bridge" ]]
[[ -f "$RUNTIME_DIR/bin/PhotoStewardPhotosBridge.app/Contents/Info.plist" ]]
[[ -d "$RUNTIME_DIR/Python3.framework" ]]
[[ ! -d "$RUNTIME_DIR/Python3.framework/Versions/3.9/lib/python3.9/site-packages" ]]
[[ -f "$RUNTIME_DIR/tools/icloud_photo_sync/cli.py" ]]
[[ -f "$RUNTIME_DIR/.runtime-manifest" ]]
[[ -f "$RUNTIME_DIR/skills/photo-steward/SKILL.md" ]]
[[ -f "$RUNTIME_DIR/skills/icloud-photo-center/SKILL.md" ]]
[[ -x "$RUNTIME_DIR/scripts/retire_launchd_agents.sh" ]]
[[ ! -e "$RUNTIME_DIR/scripts/install_launchd_agents.sh" ]]
[[ ! -e "$RUNTIME_DIR/scripts/run_weekly_orchestrator.sh" ]]
[[ ! -e "$RUNTIME_DIR/scripts/run_nas_maintenance.sh" ]]
[[ -x "$RUNTIME_DIR/scripts/nas/photo_steward_nas_worker.py" ]]
[[ -x "$RUNTIME_DIR/scripts/nas/install_synology_worker.sh" ]]

file "$RUNTIME_DIR/bin/PhotoStewardPhotosBridge.app/Contents/MacOS/photos_bridge" | rg -Fq 'universal binary'
file "$RUNTIME_DIR/Python3.framework/Versions/3.9/bin/python3" | rg -Fq 'universal binary'
"$RUNTIME_DIR/bin/python3" -c 'import sqlite3, tomli; assert tomli.loads("ok = true")["ok"]; print(sqlite3.sqlite_version)'
PYTHONPATH="$RUNTIME_DIR/vendor:$RUNTIME_DIR" \
  "$RUNTIME_DIR/bin/python3" -m tools.icloud_photo_sync.cli --help >/dev/null
[[ -z "$(find "$RUNTIME_DIR/tools" "$RUNTIME_DIR/vendor" -name '__pycache__' -print -quit)" ]]

print "runtime_bundle: manual runtime, bridge, CLI, Skill, and legacy scheduler retirement are executable"
