#!/bin/zsh
set -euo pipefail

RUNTIME_ROOT="${1:?runtime root is required}"
SIGNING_IDENTITY="${2:?signing identity is required}"
PYTHON_VERSION_ROOT="$RUNTIME_ROOT/Python3.framework/Versions/3.9"
PYTHON_APP="$PYTHON_VERSION_ROOT/Resources/Python.app"
PHOTOS_BRIDGE_APP="$RUNTIME_ROOT/bin/PhotoStewardPhotosBridge.app"
PHOTOS_BRIDGE_BINARY="$PHOTOS_BRIDGE_APP/Contents/MacOS/photos_bridge"

for path in \
  "$PYTHON_VERSION_ROOT/Python3" \
  "$PYTHON_VERSION_ROOT/bin/python3.9" \
  "$PYTHON_APP/Contents/MacOS/Python" \
  "$PYTHON_APP" \
  "$RUNTIME_ROOT/Python3.framework" \
  "$PHOTOS_BRIDGE_BINARY"; do
  [[ -e "$path" ]] || { echo "runtime code is missing: $path" >&2; exit 1; }
  /usr/bin/codesign --force --options runtime --timestamp --sign "$SIGNING_IDENTITY" "$path"
done
/usr/bin/codesign --force --options runtime --timestamp --sign "$SIGNING_IDENTITY" "$PHOTOS_BRIDGE_APP"
