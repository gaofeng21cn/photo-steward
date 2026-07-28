#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT

HOME="$TMP_HOME" CODEX_HOME="$TMP_HOME/.codex" "$ROOT_DIR/scripts/install_local.sh" >/dev/null

[[ -L "$TMP_HOME/.local/bin/photo-steward" ]]
[[ "$(readlink "$TMP_HOME/.local/bin/photo-steward")" == "$ROOT_DIR/scripts/icloud-photo-sync" ]]
[[ -L "$TMP_HOME/.local/bin/icloud-photo-sync" ]]
[[ "$(readlink "$TMP_HOME/.local/bin/icloud-photo-sync")" == "$ROOT_DIR/scripts/icloud-photo-sync" ]]
[[ -L "$TMP_HOME/.codex/skills/photo-steward" ]]
[[ "$(readlink "$TMP_HOME/.codex/skills/photo-steward")" == "$ROOT_DIR/skills/icloud-photo-center" ]]
[[ -L "$TMP_HOME/.codex/skills/icloud-photo-center" ]]
[[ "$(readlink "$TMP_HOME/.codex/skills/icloud-photo-center")" == "$ROOT_DIR/skills/icloud-photo-center" ]]

CONFIG_PATH="$TMP_HOME/Library/Application Support/Photo Steward/config.toml"
[[ -f "$CONFIG_PATH" ]]
[[ "$(stat -f '%Lp' "$CONFIG_PATH")" == "600" ]]
[[ -f "$TMP_HOME/Library/Application Support/Photo Steward/active-config-path" ]]
print -r -- "# existing-config-sentinel" >> "$CONFIG_PATH"
HOME="$TMP_HOME" CODEX_HOME="$TMP_HOME/.codex" "$ROOT_DIR/scripts/install_local.sh" >/dev/null
rg -Fq '# existing-config-sentinel' "$CONFIG_PATH"

print "install_local: primary and compatibility entry points plus private config installed"
