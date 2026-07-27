#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
SKILL_ROOT="${CODEX_HOME:-${HOME}/.codex}/skills"

mkdir -p "$BIN_DIR" "$SKILL_ROOT"
chmod +x "$ROOT_DIR/scripts/icloud-photo-sync"
ln -sfn "$ROOT_DIR/scripts/icloud-photo-sync" "$BIN_DIR/icloud-photo-sync"
ln -sfn "$ROOT_DIR/skills/icloud-photo-center" "$SKILL_ROOT/icloud-photo-center"

printf '%s\n' \
  "$BIN_DIR/icloud-photo-sync" \
  "$SKILL_ROOT/icloud-photo-center"
