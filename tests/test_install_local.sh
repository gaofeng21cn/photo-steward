#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT

HOME="$TMP_HOME" CODEX_HOME="$TMP_HOME/.codex" "$ROOT_DIR/scripts/install_local.sh" >/dev/null

[[ -L "$TMP_HOME/.local/bin/icloud-photo-sync" ]]
[[ "$(readlink "$TMP_HOME/.local/bin/icloud-photo-sync")" == "$ROOT_DIR/scripts/icloud-photo-sync" ]]
[[ -L "$TMP_HOME/.codex/skills/icloud-photo-center" ]]
[[ "$(readlink "$TMP_HOME/.codex/skills/icloud-photo-center")" == "$ROOT_DIR/skills/icloud-photo-center" ]]
print "install_local: CLI and Skill links installed"
