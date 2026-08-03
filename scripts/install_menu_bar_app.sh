#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="Photo Steward.app"
APP_DIR="${HOME}/Applications/${APP_NAME}"
LEGACY_APP_DIR="${HOME}/Applications/iCloud Photo Center.app"
BUILD_DIR="$ROOT_DIR/app/PhotoCenterMenuBar/.build/release"
SIGNING_IDENTITY="${PHOTO_CENTER_SIGNING_IDENTITY:-}"
RUNTIME_DIR="$ROOT_DIR/tmp/photo-steward-local-runtime"
ENTITLEMENTS="$ROOT_DIR/app/PhotoCenterMenuBar/PhotoSteward.entitlements"

if [[ -z "$SIGNING_IDENTITY" ]]; then
  SIGNING_IDENTITY="$(
    security find-identity -v -p codesigning |
      sed -n 's/^[[:space:]]*[0-9]*) [0-9A-F]* "\(Developer ID Application:.*\)"/\1/p' |
      head -1
  )"
fi

swift build --package-path "$ROOT_DIR/app/PhotoCenterMenuBar" -c release
"$ROOT_DIR/scripts/stage_runtime.sh" "$RUNTIME_DIR" >/dev/null

rm -rf "$APP_DIR"
if [[ "$LEGACY_APP_DIR" != "$APP_DIR" ]]; then
  rm -rf "$LEGACY_APP_DIR"
fi
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"
cp "$BUILD_DIR/PhotoCenterMenuBar" "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"
cp "$ROOT_DIR/app/PhotoCenterMenuBar/Info.plist" "$APP_DIR/Contents/Info.plist"
cp "$ROOT_DIR/app/PhotoCenterMenuBar/Resources/PhotoSteward.icns" "$APP_DIR/Contents/Resources/PhotoSteward.icns"
ditto "$RUNTIME_DIR" "$APP_DIR/Contents/Resources/PhotoStewardRuntime"
chmod +x "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"
if [[ -n "$SIGNING_IDENTITY" ]] &&
  security find-identity -v -p codesigning | grep -Fq "\"$SIGNING_IDENTITY\""; then
  "$ROOT_DIR/scripts/sign_runtime.sh" \
    "$APP_DIR/Contents/Resources/PhotoStewardRuntime" \
    "$SIGNING_IDENTITY" \
    "$ENTITLEMENTS"
  if ! codesign \
    --force \
    --options runtime \
    --entitlements "$ENTITLEMENTS" \
    --sign "$SIGNING_IDENTITY" \
    "$APP_DIR"; then
    echo "Developer ID signing unavailable; falling back to ad-hoc signing" >&2
    codesign --force --entitlements "$ENTITLEMENTS" --sign - "$APP_DIR"
  fi
else
  "$ROOT_DIR/scripts/sign_runtime.sh" \
    "$APP_DIR/Contents/Resources/PhotoStewardRuntime" \
    - \
    "$ENTITLEMENTS"
  codesign --force --entitlements "$ENTITLEMENTS" --sign - "$APP_DIR"
fi

printf '%s\n' "$APP_DIR"
