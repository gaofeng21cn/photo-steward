#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_DIR="${1:-$ROOT_DIR/tmp/photo-steward-runtime}"
BUILD_DIR="$ROOT_DIR/tmp/photo-steward-bridge-build"
PYTHON_FRAMEWORK="${PHOTO_STEWARD_PYTHON_FRAMEWORK:-/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework}"
TOMLI_SOURCE="${PHOTO_STEWARD_TOMLI_SOURCE:-}"

if [[ ! -d "$PYTHON_FRAMEWORK" ]]; then
  echo "Universal Python3.framework not found: $PYTHON_FRAMEWORK" >&2
  echo "Set PHOTO_STEWARD_PYTHON_FRAMEWORK to a universal Python 3.9 framework." >&2
  exit 1
fi

if [[ -z "$TOMLI_SOURCE" ]]; then
  for candidate in \
    "/opt/homebrew/lib/python3.9/site-packages/pip/_vendor/tomli" \
    "/opt/homebrew/lib/python3.11/site-packages/pip/_vendor/tomli" \
    "$HOME/.py-global/lib/python3.12/site-packages/pip/_vendor/tomli"; do
    if [[ -d "$candidate" ]]; then
      TOMLI_SOURCE="$candidate"
      break
    fi
  done
fi
if [[ ! -d "$TOMLI_SOURCE" ]]; then
  echo "tomli source not found; set PHOTO_STEWARD_TOMLI_SOURCE." >&2
  exit 1
fi

/bin/rm -rf "$OUTPUT_DIR" "$BUILD_DIR"
mkdir -p \
  "$OUTPUT_DIR/bin" \
  "$OUTPUT_DIR/vendor" \
  "$OUTPUT_DIR/scripts/lib" \
  "$OUTPUT_DIR/skills/photo-steward" \
  "$OUTPUT_DIR/skills/icloud-photo-center"

/usr/bin/rsync -a --exclude '__pycache__' --exclude '*.pyc' "$ROOT_DIR/tools/" "$OUTPUT_DIR/tools/"
/usr/bin/ditto "$ROOT_DIR/skills/icloud-photo-center" "$OUTPUT_DIR/skills/photo-steward"
/usr/bin/ditto "$ROOT_DIR/skills/icloud-photo-center" "$OUTPUT_DIR/skills/icloud-photo-center"
/usr/bin/ditto "$ROOT_DIR/scripts/lib/automation_common.sh" "$OUTPUT_DIR/scripts/lib/automation_common.sh"
for script_name in \
  icloud-photo-sync \
  run_plan.sh \
  run_apply_latest.sh \
  run_deleted_pool_retention.sh \
  run_onedrive_backup.sh \
  run_todo_plan.sh \
  install_launchd_agents.sh \
  install_launchd_todo_agent.sh; do
  /usr/bin/ditto "$ROOT_DIR/scripts/$script_name" "$OUTPUT_DIR/scripts/$script_name"
done
/usr/bin/rsync -a --exclude '__pycache__' --exclude '*.pyc' "$TOMLI_SOURCE/" "$OUTPUT_DIR/vendor/tomli/"
/usr/bin/ditto "$PYTHON_FRAMEWORK" "$OUTPUT_DIR/Python3.framework"
/bin/rm -rf "$OUTPUT_DIR/Python3.framework/Versions/3.9/lib/python3.9/site-packages"

mkdir -p "$BUILD_DIR"
for architecture in arm64 x86_64; do
  scratch_path="$BUILD_DIR/$architecture"
  /usr/bin/swiftc \
    "$ROOT_DIR/tools/icloud_photo_sync/photos_bridge.swift" \
    -target "$architecture-apple-macosx13.0" \
    -o "$scratch_path" \
    -framework Photos
done
/usr/bin/lipo "$BUILD_DIR/arm64" "$BUILD_DIR/x86_64" -create -output "$OUTPUT_DIR/bin/photos_bridge"
/bin/chmod +x "$OUTPUT_DIR/bin/photos_bridge"

cat > "$OUTPUT_DIR/bin/python3" <<'PYTHON_WRAPPER'
#!/bin/zsh
set -euo pipefail
RUNTIME_ROOT="${0:A:h:h}"
export PYTHONHOME="$RUNTIME_ROOT/Python3.framework/Versions/3.9"
export PYTHONPATH="$RUNTIME_ROOT/vendor:$RUNTIME_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHONHOME/bin/python3" "$@"
PYTHON_WRAPPER
chmod +x "$OUTPUT_DIR/bin/python3"

cat > "$OUTPUT_DIR/THIRD-PARTY-NOTICES.txt" <<'NOTICES'
Photo Steward bundles the following runtime components:

Python 3.9
Copyright (c) Python Software Foundation.
Python is distributed under the Python Software Foundation License.

tomli
Copyright (c) 2021 Timothée Mazzucotelli.
tomli is distributed under the MIT License.
NOTICES

(
  cd "$OUTPUT_DIR"
  find bin scripts skills tools vendor -type f | LC_ALL=C sort | while IFS= read -r file_path; do
    /usr/bin/shasum -a 256 "$file_path"
  done
) | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}' > "$OUTPUT_DIR/.runtime-manifest"

print -r -- "$OUTPUT_DIR"
