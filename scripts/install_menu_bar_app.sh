#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="iCloud Photo Center.app"
APP_DIR="${HOME}/Applications/${APP_NAME}"
BUILD_DIR="$ROOT_DIR/app/PhotoCenterMenuBar/.build/release"
SIGNING_IDENTITY="${PHOTO_CENTER_SIGNING_IDENTITY:-}"

if [[ -z "$SIGNING_IDENTITY" ]]; then
  SIGNING_IDENTITY="$(
    security find-identity -v -p codesigning |
      sed -n 's/^[[:space:]]*[0-9]*) [0-9A-F]* "\(Developer ID Application:.*\)"/\1/p' |
      head -1
  )"
fi

swift build --package-path "$ROOT_DIR/app/PhotoCenterMenuBar" -c release

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
cp "$BUILD_DIR/PhotoCenterMenuBar" "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"
cp "$ROOT_DIR/app/PhotoCenterMenuBar/Info.plist" "$APP_DIR/Contents/Info.plist"
chmod +x "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"
if [[ -n "$SIGNING_IDENTITY" ]] &&
  security find-identity -v -p codesigning | grep -Fq "\"$SIGNING_IDENTITY\""; then
  if ! codesign --force --deep --options runtime --sign "$SIGNING_IDENTITY" "$APP_DIR"; then
    echo "Developer ID signing unavailable; falling back to ad-hoc signing" >&2
    codesign --force --deep --sign - "$APP_DIR"
  fi
else
  codesign --force --deep --sign - "$APP_DIR"
fi

printf '%s\n' "$APP_DIR"
