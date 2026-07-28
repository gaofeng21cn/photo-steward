#!/bin/zsh
set -euo pipefail

RUNTIME_ROOT="${1:?runtime root is required}"
SIGNING_IDENTITY="${2:?signing identity is required}"
PYTHON_VERSION_ROOT="$RUNTIME_ROOT/Python3.framework/Versions/3.9"
PYTHON_APP="$PYTHON_VERSION_ROOT/Resources/Python.app"

for path in \
  "$PYTHON_VERSION_ROOT/Python3" \
  "$PYTHON_VERSION_ROOT/bin/python3.9" \
  "$PYTHON_APP/Contents/MacOS/Python" \
  "$PYTHON_APP" \
  "$RUNTIME_ROOT/Python3.framework" \
  "$RUNTIME_ROOT/bin/photos_bridge"; do
  [[ -e "$path" ]] || { echo "runtime code is missing: $path" >&2; exit 1; }
  /usr/bin/codesign --force --options runtime --timestamp --sign "$SIGNING_IDENTITY" "$path"
done
