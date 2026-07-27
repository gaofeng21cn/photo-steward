#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="iCloud Photo Center.app"
APP_DIR="${HOME}/Applications/${APP_NAME}"
BUILD_DIR="$ROOT_DIR/app/PhotoCenterMenuBar/.build/release"
SIGNING_IDENTITY="${PHOTO_CENTER_SIGNING_IDENTITY:-Developer ID Application: FENG GAO (SVVC4TA784)}"

swift build --package-path "$ROOT_DIR/app/PhotoCenterMenuBar" -c release

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
cp "$BUILD_DIR/PhotoCenterMenuBar" "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"
cp "$ROOT_DIR/app/PhotoCenterMenuBar/Info.plist" "$APP_DIR/Contents/Info.plist"
printf '%s\n' "$ROOT_DIR" > "$APP_DIR/Contents/Resources/repository-root.txt"
chmod +x "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"
if security find-identity -v -p codesigning | grep -Fq "\"$SIGNING_IDENTITY\""; then
  codesign --force --deep --options runtime --sign "$SIGNING_IDENTITY" "$APP_DIR"
else
  codesign --force --deep --sign - "$APP_DIR"
fi

printf '%s\n' "$APP_DIR"
