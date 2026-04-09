#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT_DIR/tmp/automation"
cd "$ROOT_DIR"

exec /usr/bin/python3 -m tools.icloud_photo_sync.cli plan "$@"

