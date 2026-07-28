#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGE_DIR="$ROOT_DIR/app/PhotoCenterMenuBar"
INFO_PLIST="$PACKAGE_DIR/Info.plist"
ICON_FILE="$PACKAGE_DIR/Resources/PhotoSteward.icns"
DIST_DIR="${PHOTO_STEWARD_DIST_DIR:-$ROOT_DIR/dist}"
BUILD_ROOT="$ROOT_DIR/tmp/photo-steward-release-build"
RUNTIME_DIR="$BUILD_ROOT/PhotoStewardRuntime"
NOTARIZE=false
NOTARY_PROFILE="${PHOTO_STEWARD_NOTARY_PROFILE:-}"
SIGNING_IDENTITY="${PHOTO_STEWARD_SIGNING_IDENTITY:-${PHOTO_CENTER_SIGNING_IDENTITY:-}}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --notarize)
      NOTARIZE=true
      shift
      ;;
    --notary-profile)
      [[ $# -ge 2 ]] || { echo "--notary-profile requires a value" >&2; exit 2; }
      NOTARY_PROFILE="$2"
      shift 2
      ;;
    *)
      echo "usage: $0 [--notarize] [--notary-profile <keychain-profile>]" >&2
      exit 2
      ;;
  esac
done

if [[ "$NOTARIZE" == true && -z "$NOTARY_PROFILE" ]]; then
  echo "--notarize requires PHOTO_STEWARD_NOTARY_PROFILE or --notary-profile." >&2
  exit 2
fi

VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$INFO_PLIST")"
APP_NAME="Photo Steward.app"
APP_DIR="$DIST_DIR/$APP_NAME"
ZIP_PATH="$DIST_DIR/Photo-Steward-$VERSION-macOS-universal.zip"

if [[ -z "$SIGNING_IDENTITY" ]]; then
  SIGNING_IDENTITY="$(
    /usr/bin/security find-identity -v -p codesigning |
      /usr/bin/sed -n 's/^[[:space:]]*[0-9]*) [0-9A-F]* "\(Developer ID Application:.*\)"/\1/p' |
      /usr/bin/head -1
  )"
fi
if [[ -z "$SIGNING_IDENTITY" ]]; then
  echo "No Developer ID Application identity is available." >&2
  exit 1
fi
if ! /usr/bin/security find-identity -v -p codesigning | /usr/bin/grep -Fq "\"$SIGNING_IDENTITY\""; then
  echo "Signing identity is not available: $SIGNING_IDENTITY" >&2
  exit 1
fi

mkdir -p "$DIST_DIR" "$BUILD_ROOT"
rm -rf "$APP_DIR" "$ZIP_PATH"
"$ROOT_DIR/scripts/stage_runtime.sh" "$RUNTIME_DIR" >/dev/null

typeset -a binaries
for architecture in arm64 x86_64; do
  triple="$architecture-apple-macosx13.0"
  scratch_path="$BUILD_ROOT/$architecture"
  /usr/bin/swift build \
    --package-path "$PACKAGE_DIR" \
    --configuration release \
    --triple "$triple" \
    --scratch-path "$scratch_path"
  binary_path="$(
    /usr/bin/swift build \
      --package-path "$PACKAGE_DIR" \
      --configuration release \
      --triple "$triple" \
      --scratch-path "$scratch_path" \
      --show-bin-path
  )/PhotoCenterMenuBar"
  [[ -x "$binary_path" ]] || { echo "Missing $architecture build: $binary_path" >&2; exit 1; }
  binaries+=("$binary_path")
done

mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
/usr/bin/lipo "${binaries[@]}" -create -output "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"
/bin/cp "$INFO_PLIST" "$APP_DIR/Contents/Info.plist"
/bin/cp "$ICON_FILE" "$APP_DIR/Contents/Resources/PhotoSteward.icns"
/usr/bin/ditto "$RUNTIME_DIR" "$APP_DIR/Contents/Resources/PhotoStewardRuntime"
/bin/chmod +x "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"
"$ROOT_DIR/scripts/sign_runtime.sh" \
  "$APP_DIR/Contents/Resources/PhotoStewardRuntime" \
  "$SIGNING_IDENTITY"
/usr/bin/codesign --force --options runtime --timestamp --sign "$SIGNING_IDENTITY" "$APP_DIR"
/usr/bin/codesign --verify --deep --strict "$APP_DIR"
/usr/bin/lipo -info "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"

/usr/bin/ditto -c -k --keepParent "$APP_DIR" "$ZIP_PATH"

if [[ "$NOTARIZE" == true ]]; then
  /usr/bin/xcrun notarytool submit "$ZIP_PATH" \
    --keychain-profile "$NOTARY_PROFILE" \
    --wait
  /usr/bin/xcrun stapler staple "$APP_DIR"
  /usr/bin/xcrun stapler validate "$APP_DIR"
  /usr/sbin/spctl --assess --type execute --verbose=4 "$APP_DIR"
  rm -f "$ZIP_PATH"
  /usr/bin/ditto -c -k --keepParent "$APP_DIR" "$ZIP_PATH"
else
  echo "Built a signed, unnotarized validation artifact. Use --notarize for public distribution." >&2
fi

printf '%s\n' "$APP_DIR" "$ZIP_PATH"
