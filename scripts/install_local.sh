#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
SKILL_ROOT="${CODEX_HOME:-${HOME}/.codex}/skills"

chmod +x "$ROOT_DIR/scripts/icloud-photo-sync"
python3 "$ROOT_DIR/scripts/manage_installation.py" link --source "$ROOT_DIR" --json >/dev/null

CONFIG_PATH="$("$BIN_DIR/photo-steward" config path)"
if [[ ! -e "$CONFIG_PATH" ]]; then
  "$BIN_DIR/photo-steward" config init >/dev/null
fi
"$BIN_DIR/photo-steward" config activate >/dev/null

printf '%s\n' \
  "$BIN_DIR/photo-steward" \
  "$BIN_DIR/icloud-photo-sync" \
  "$SKILL_ROOT/photo-steward" \
  "$CONFIG_PATH"
