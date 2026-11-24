#!/bin/zsh
set -euo pipefail

RUNTIME_ROOT="${1:?runtime root is required}"
SIGNING_IDENTITY="${2:?signing identity is required}"
ENTITLEMENTS="${3:?entitlements path is required}"
PYTHON_VERSION_ROOT="$RUNTIME_ROOT/Python.framework/Versions/3.13"
PYTHON_BINARY="$PYTHON_VERSION_ROOT/bin/python3.13"
PYTHON_APP="$PYTHON_VERSION_ROOT/Resources/Python.app"
typeset -a runtime_args
if [[ "$SIGNING_IDENTITY" != "-" ]]; then
  runtime_args=(--options runtime --timestamp)
fi

while IFS= read -r runtime_file; do
  [[ -e "$runtime_file" ]] || { echo "runtime code is missing: $runtime_file" >&2; exit 1; }
  /usr/bin/codesign \
    --force \
    "${runtime_args[@]}" \
    --sign "$SIGNING_IDENTITY" \
    "$runtime_file"
done < <(python3 - "$RUNTIME_ROOT/Python.framework" <<'PY'
from pathlib import Path
import sys
magic = {b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}
for path in sorted(Path(sys.argv[1]).rglob('*')):
    if path.is_file() and not path.is_symlink():
        with path.open('rb') as stream:
            if stream.read(4) in magic:
                print(path)
PY
)
for runtime_file in "$PYTHON_BINARY" "$PYTHON_APP"; do
  /usr/bin/codesign \
    --force \
    "${runtime_args[@]}" \
    --entitlements "$ENTITLEMENTS" \
    --sign "$SIGNING_IDENTITY" \
    "$runtime_file"
done
/usr/bin/codesign \
  --force \
  "${runtime_args[@]}" \
  --sign "$SIGNING_IDENTITY" \
  "$RUNTIME_ROOT/Python.framework"
