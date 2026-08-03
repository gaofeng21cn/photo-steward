#!/bin/zsh
set -euo pipefail

RUNTIME_ROOT="${1:?runtime root is required}"
SIGNING_IDENTITY="${2:?signing identity is required}"
ENTITLEMENTS="${3:?entitlements path is required}"
PYTHON_VERSION_ROOT="$RUNTIME_ROOT/Python3.framework/Versions/3.9"
PYTHON_APP="$PYTHON_VERSION_ROOT/Resources/Python.app"
PHOTOS_BRIDGE_APP="$RUNTIME_ROOT/bin/PhotoStewardPhotosBridge.app"
PHOTOS_BRIDGE_BINARY="$PHOTOS_BRIDGE_APP/Contents/MacOS/photos_bridge"
typeset -a timestamp_args
if [[ "$SIGNING_IDENTITY" != "-" ]]; then
  timestamp_args=(--timestamp)
fi

for path in \
  "$PYTHON_VERSION_ROOT/Python3" \
  "$PYTHON_VERSION_ROOT/bin/python3.9" \
  "$PYTHON_APP/Contents/MacOS/Python" \
  "$PYTHON_APP" \
  "$RUNTIME_ROOT/Python3.framework"; do
  [[ -e "$path" ]] || { echo "runtime code is missing: $path" >&2; exit 1; }
  /usr/bin/codesign \
    --force \
    --options runtime \
    "${timestamp_args[@]}" \
    --sign "$SIGNING_IDENTITY" \
    "$path"
done
/usr/bin/codesign \
  --force \
  --options runtime \
  "${timestamp_args[@]}" \
  --entitlements "$ENTITLEMENTS" \
  --sign "$SIGNING_IDENTITY" \
  "$PHOTOS_BRIDGE_BINARY"
/usr/bin/codesign \
  --force \
  --options runtime \
  "${timestamp_args[@]}" \
  --entitlements "$ENTITLEMENTS" \
  --sign "$SIGNING_IDENTITY" \
  "$PHOTOS_BRIDGE_APP"
