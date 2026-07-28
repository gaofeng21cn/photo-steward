#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
SKILL_ROOT="${CODEX_HOME:-${HOME}/.codex}/skills"

mkdir -p "$BIN_DIR" "$SKILL_ROOT"
chmod +x "$ROOT_DIR/scripts/icloud-photo-sync"
ln -sfn "$ROOT_DIR/scripts/icloud-photo-sync" "$BIN_DIR/photo-steward"
ln -sfn "$ROOT_DIR/scripts/icloud-photo-sync" "$BIN_DIR/icloud-photo-sync"
ln -sfn "$ROOT_DIR/skills/icloud-photo-center" "$SKILL_ROOT/photo-steward"
ln -sfn "$ROOT_DIR/skills/icloud-photo-center" "$SKILL_ROOT/icloud-photo-center"

CONFIG_PATH="$("$BIN_DIR/photo-steward" config path)"
if [[ ! -e "$CONFIG_PATH" ]]; then
  "$BIN_DIR/photo-steward" config init >/dev/null
fi
"$BIN_DIR/photo-steward" config activate >/dev/null

printf '%s\n' \
  "$BIN_DIR/photo-steward" \
  "$BIN_DIR/icloud-photo-sync" \
  "$SKILL_ROOT/photo-steward" \
  "$SKILL_ROOT/icloud-photo-center" \
  "$CONFIG_PATH"
