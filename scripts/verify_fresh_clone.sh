#!/bin/zsh
set -euo pipefail

SOURCE="${1:-https://github.com/gaofeng21cn/photo-steward.git}"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/photo-steward-fresh-clone.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT
CLONE_DIR="$TMP_ROOT/photo-steward"

if [[ "$SOURCE" == /* ]]; then
  SOURCE="file://$SOURCE"
fi
git clone --depth 1 "$SOURCE" "$CLONE_DIR"
cd "$CLONE_DIR"

[[ -f LICENSE ]]
[[ -f README.md ]]
[[ -f README.zh-CN.md ]]
[[ -f config/photo-steward.example.toml ]]
[[ ! -e state ]]
[[ ! -e tmp ]]

if git grep -n -I -E '/Users/gaofeng|/Volumes/home|Gaofeng-Home|hotmail\.com' \
  -- ':!LICENSE' ':!scripts/verify_fresh_clone.sh'; then
  echo "fresh clone contains a personal/runtime marker" >&2
  exit 1
fi

python3 -m pytest tests -q
swift build --package-path app/PhotoCenterMenuBar -c release
printf '%s\n' 'fresh clone validation passed'
