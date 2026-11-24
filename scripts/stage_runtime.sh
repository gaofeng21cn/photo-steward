#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_DIR="${1:-$ROOT_DIR/tmp/photo-steward-runtime}"
/bin/rm -rf "$OUTPUT_DIR"
mkdir -p \
  "$OUTPUT_DIR/bin" \
  "$OUTPUT_DIR/scripts/lib" \
  "$OUTPUT_DIR/scripts/nas" \
  "$OUTPUT_DIR/skills/photo-steward"

/usr/bin/rsync -a --exclude '__pycache__' --exclude '*.pyc' "$ROOT_DIR/tools/" "$OUTPUT_DIR/tools/"
/usr/bin/ditto "$ROOT_DIR/skills/photo-steward" "$OUTPUT_DIR/skills/photo-steward"
/usr/bin/ditto "$ROOT_DIR/opl-package.json" "$OUTPUT_DIR/opl-package.json"
/usr/bin/ditto "$ROOT_DIR/scripts/lib/automation_common.sh" "$OUTPUT_DIR/scripts/lib/automation_common.sh"
for script_name in \
  icloud-photo-sync \
  manage_installation.py \
  run_plan.sh \
  run_apply_latest.sh \
  run_deleted_pool_retention.sh \
  run_onedrive_backup.sh \
  run_todo_plan.sh \
  retire_launchd_agents.sh; do
  /usr/bin/ditto "$ROOT_DIR/scripts/$script_name" "$OUTPUT_DIR/scripts/$script_name"
done
/usr/bin/ditto "$ROOT_DIR/scripts/nas/photo_steward_nas_worker.py" "$OUTPUT_DIR/scripts/nas/photo_steward_nas_worker.py"
/usr/bin/ditto "$ROOT_DIR/scripts/nas/install_synology_worker.sh" "$OUTPUT_DIR/scripts/nas/install_synology_worker.sh"
python3 "$ROOT_DIR/scripts/prepare_python_runtime.py" "$OUTPUT_DIR/Python.framework" >/dev/null

cat > "$OUTPUT_DIR/bin/python3" <<'PYTHON_WRAPPER'
#!/bin/zsh
set -euo pipefail
RUNTIME_ROOT="${0:A:h:h}"
export PYTHONHOME="$RUNTIME_ROOT/Python.framework/Versions/3.13"
export PYTHONPATH="$RUNTIME_ROOT"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export SSL_CERT_FILE="${SSL_CERT_FILE:-/etc/ssl/cert.pem}"
exec "$PYTHONHOME/bin/python3.13" "$@"
PYTHON_WRAPPER
chmod +x "$OUTPUT_DIR/bin/python3"

cat > "$OUTPUT_DIR/THIRD-PARTY-NOTICES.txt" <<'NOTICES'
Photo Steward bundles the following runtime components:

Python 3.13.14
Copyright (c) Python Software Foundation.
Python is distributed under the Python Software Foundation License.

osxphotos (and its Python runtime dependencies)
Copyright (c) Rhet Turnbull.
osxphotos is distributed under the MIT License.
NOTICES

(
  cd "$OUTPUT_DIR"
  find bin scripts skills tools opl-package.json python-runtime.json THIRD-PARTY-NOTICES.txt -type f | LC_ALL=C sort | while IFS= read -r file_path; do
    /usr/bin/shasum -a 256 "$file_path"
  done
) | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}' > "$OUTPUT_DIR/.runtime-manifest"

print -r -- "$OUTPUT_DIR"
