#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="Photo Steward.app"
TARGET_APP_DIR="${PHOTO_STEWARD_APP_DIR:-${HOME}/Applications/Photo Steward Development/${APP_NAME}}"
APP_DIR="$ROOT_DIR/tmp/photo-steward-local-build/$APP_NAME"
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
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"
cp "$BUILD_DIR/PhotoCenterMenuBar" "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"
cp "$ROOT_DIR/app/PhotoCenterMenuBar/Info.plist" "$APP_DIR/Contents/Info.plist"
/usr/bin/plutil -insert PhotoStewardDevelopmentBuild -bool true "$APP_DIR/Contents/Info.plist"
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

VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$APP_DIR/Contents/Info.plist")"
typeset -a revision_args
if [[ -e "$TARGET_APP_DIR" ]]; then
  revision="$(python3 "$ROOT_DIR/scripts/manage_installation.py" inspect --app-path "$TARGET_APP_DIR" --json |
    python3 -c 'import json,sys; p=sys.argv[1]; rows=json.load(sys.stdin)["installations"]; print(next(row["revision"] for row in rows if row["location"] == p))' "$TARGET_APP_DIR")"
  revision_args=(--expected-revision "$revision")
fi
python3 "$ROOT_DIR/scripts/manage_installation.py" install-bundle --development \
  --bundle "$APP_DIR" --app-path "$TARGET_APP_DIR" --version "$VERSION" "${revision_args[@]}" --json
