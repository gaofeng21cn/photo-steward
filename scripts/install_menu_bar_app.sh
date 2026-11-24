#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="Photo Steward.app"
TARGET_APP_DIR="${PHOTO_STEWARD_APP_DIR:-${HOME}/Applications/Photo Steward Development/${APP_NAME}}"
APP_DIR="$ROOT_DIR/tmp/photo-steward-local-build/$APP_NAME"
PACKAGE_DIR="$ROOT_DIR/app/PhotoCenterMenuBar"
BUILD_DIR="$PACKAGE_DIR/.build/release"
SIGNING_IDENTITY="${PHOTO_CENTER_SIGNING_IDENTITY:-}"
RUNTIME_DIR="$ROOT_DIR/tmp/photo-steward-local-runtime"
ENTITLEMENTS="$PACKAGE_DIR/PhotoSteward.entitlements"

if [[ -z "$SIGNING_IDENTITY" ]]; then
  SIGNING_IDENTITY="$(
    security find-identity -v -p codesigning |
      sed -n 's/^[[:space:]]*[0-9]*) [0-9A-F]* "\(Developer ID Application:.*\)"/\1/p' |
      head -1
  )"
fi

swift build --package-path "$PACKAGE_DIR" -c release
"$ROOT_DIR/scripts/stage_runtime.sh" "$RUNTIME_DIR" >/dev/null

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"
cp "$BUILD_DIR/PhotoCenterMenuBar" "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"
cp "$PACKAGE_DIR/Info.plist" "$APP_DIR/Contents/Info.plist"
/usr/bin/plutil -insert PhotoStewardDevelopmentBuild -bool true "$APP_DIR/Contents/Info.plist"
cp "$PACKAGE_DIR/Resources/PhotoSteward.icns" "$APP_DIR/Contents/Resources/PhotoSteward.icns"
ditto "$RUNTIME_DIR" "$APP_DIR/Contents/Resources/PhotoStewardRuntime"
chmod +x "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"

EFFECTIVE_IDENTITY="-"
if [[ -n "$SIGNING_IDENTITY" ]] &&
  security find-identity -v -p codesigning | grep -Fq "\"$SIGNING_IDENTITY\""; then
  EFFECTIVE_IDENTITY="$SIGNING_IDENTITY"
fi

if [[ "$EFFECTIVE_IDENTITY" != "-" ]]; then
  "$ROOT_DIR/scripts/embed_sparkle.sh" \
    --app "$APP_DIR" \
    --signing-identity "$EFFECTIVE_IDENTITY" \
    --artifacts-dir "$PACKAGE_DIR/.build/artifacts"
  "$ROOT_DIR/scripts/sign_runtime.sh" \
    "$APP_DIR/Contents/Resources/PhotoStewardRuntime" \
    "$EFFECTIVE_IDENTITY" \
    "$ENTITLEMENTS"
  if ! codesign \
    --force \
    --options runtime \
    --entitlements "$ENTITLEMENTS" \
    --sign "$EFFECTIVE_IDENTITY" \
    "$APP_DIR"; then
    echo "Developer ID signing unavailable; falling back to ad-hoc signing" >&2
    "$ROOT_DIR/scripts/embed_sparkle.sh" \
      --app "$APP_DIR" \
      --signing-identity - \
      --artifacts-dir "$PACKAGE_DIR/.build/artifacts"
    codesign --force --entitlements "$ENTITLEMENTS" --sign - "$APP_DIR"
  fi
else
  "$ROOT_DIR/scripts/embed_sparkle.sh" \
    --app "$APP_DIR" \
    --signing-identity - \
    --artifacts-dir "$PACKAGE_DIR/.build/artifacts"
  "$ROOT_DIR/scripts/sign_runtime.sh" \
    "$APP_DIR/Contents/Resources/PhotoStewardRuntime" \
    - \
    "$ENTITLEMENTS"
  codesign --force --entitlements "$ENTITLEMENTS" --sign - "$APP_DIR"
fi

mkdir -p "$(dirname "$TARGET_APP_DIR")"
rm -rf "$TARGET_APP_DIR"
ditto "$APP_DIR" "$TARGET_APP_DIR"
python3 "$ROOT_DIR/scripts/manage_installation.py" prepare --app-path "$TARGET_APP_DIR" --json
