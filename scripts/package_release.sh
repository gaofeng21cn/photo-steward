#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGE_DIR="$ROOT_DIR/app/PhotoCenterMenuBar"
INFO_PLIST="$PACKAGE_DIR/Info.plist"
ENTITLEMENTS="$PACKAGE_DIR/PhotoSteward.entitlements"
ICON_FILE="$PACKAGE_DIR/Resources/PhotoSteward.icns"
DIST_DIR="${PHOTO_STEWARD_DIST_DIR:-$ROOT_DIR/dist}"
BUILD_ROOT="$ROOT_DIR/tmp/photo-steward-release-build"
RUNTIME_DIR="$BUILD_ROOT/PhotoStewardRuntime"
APP_ONLY=false
NOTARIZE=false
NOTARY_PROFILE="${PHOTO_STEWARD_NOTARY_PROFILE:-}"
SIGNING_IDENTITY="${PHOTO_STEWARD_SIGNING_IDENTITY:-${OPL_SIGNING_IDENTITY:-${PHOTO_CENTER_SIGNING_IDENTITY:-}}}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-only)
      APP_ONLY=true
      shift
      ;;
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
      echo "usage: $0 [--app-only] [--notarize] [--notary-profile <keychain-profile>]" >&2
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
DMG_PATH="$DIST_DIR/Photo-Steward.dmg"
CHECKSUM_PATH="$DMG_PATH.sha256"

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
rm -rf "$APP_DIR"
if [[ "$APP_ONLY" != true ]]; then
  rm -f "$DMG_PATH" "$CHECKSUM_PATH" "$DIST_DIR/appcast.xml"
fi
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

SPARKLE_ARTIFACTS_DIR="$BUILD_ROOT/arm64/artifacts"
if [[ -d "$SPARKLE_ARTIFACTS_DIR" ]]; then
  # Expose Sparkle CLI tools at repo-root .build/artifacts for the shared OPL Sparkle release workflow.
  mkdir -p "$ROOT_DIR/.build"
  ln -sfn "$SPARKLE_ARTIFACTS_DIR" "$ROOT_DIR/.build/artifacts"
fi

mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
/usr/bin/lipo "${binaries[@]}" -create -output "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"
/usr/bin/strip -S "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"
/bin/cp "$INFO_PLIST" "$APP_DIR/Contents/Info.plist"
/bin/cp "$ICON_FILE" "$APP_DIR/Contents/Resources/PhotoSteward.icns"
/usr/bin/ditto "$RUNTIME_DIR" "$APP_DIR/Contents/Resources/PhotoStewardRuntime"
/bin/chmod +x "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"

"$ROOT_DIR/scripts/embed_sparkle.sh" \
  --app "$APP_DIR" \
  --signing-identity "$SIGNING_IDENTITY" \
  --artifacts-dir "$SPARKLE_ARTIFACTS_DIR" \
  --archs "arm64 x86_64"
"$ROOT_DIR/scripts/sign_runtime.sh" \
  "$APP_DIR/Contents/Resources/PhotoStewardRuntime" \
  "$SIGNING_IDENTITY" \
  "$ENTITLEMENTS"
/usr/bin/codesign \
  --force \
  --options runtime \
  --timestamp \
  --entitlements "$ENTITLEMENTS" \
  --sign "$SIGNING_IDENTITY" \
  "$APP_DIR"
/usr/bin/codesign --verify --deep --strict "$APP_DIR"
/usr/bin/lipo -info "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"

if [[ "$APP_ONLY" == true ]]; then
  printf '%s\n' "$APP_DIR"
  exit 0
fi

TEMP_DMG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/photo-steward-dmg.XXXXXX")"
trap 'rm -rf "${TEMP_DMG_DIR:?}"' EXIT INT TERM

if [[ "$NOTARIZE" == true ]]; then
  APP_ZIP="$TEMP_DMG_DIR/Photo-Steward-app.zip"
  /usr/bin/ditto -c -k --keepParent "$APP_DIR" "$APP_ZIP"
  /usr/bin/xcrun notarytool submit "$APP_ZIP" \
    --keychain-profile "$NOTARY_PROFILE" \
    --wait
  /usr/bin/xcrun stapler staple "$APP_DIR"
  /usr/bin/xcrun stapler validate "$APP_DIR"
  /usr/sbin/spctl --assess --type execute --verbose=4 "$APP_DIR"
fi

DMG_STAGING="$TEMP_DMG_DIR/staging"
mkdir -p "$DMG_STAGING"
/usr/bin/ditto "$APP_DIR" "$DMG_STAGING/$APP_NAME"
/bin/ln -s /Applications "$DMG_STAGING/Applications"
/usr/bin/hdiutil create \
  -volname "Photo Steward" \
  -srcfolder "$DMG_STAGING" \
  -format UDZO \
  -ov \
  "$DMG_PATH"
/usr/bin/hdiutil verify "$DMG_PATH"
/usr/bin/codesign --force --sign "$SIGNING_IDENTITY" --timestamp "$DMG_PATH"
/usr/bin/codesign --verify --verbose=2 "$DMG_PATH"

if [[ "$NOTARIZE" == true ]]; then
  /usr/bin/xcrun notarytool submit "$DMG_PATH" \
    --keychain-profile "$NOTARY_PROFILE" \
    --wait
  /usr/bin/xcrun stapler staple "$DMG_PATH"
  /usr/bin/xcrun stapler validate "$DMG_PATH"
  /usr/sbin/spctl --assess --type open --context context:primary-signature --verbose=4 "$DMG_PATH"
  (
    cd "$DIST_DIR"
    /usr/bin/shasum -a 256 "${DMG_PATH:t}" > "${CHECKSUM_PATH:t}"
  )
  PHOTO_STEWARD_RELEASE_TAG="v$VERSION" \
  PHOTO_STEWARD_APP_PATH="$APP_DIR" \
  PHOTO_STEWARD_EXPECT_UNIVERSAL=1 \
    "$ROOT_DIR/scripts/generate_appcast.sh" "$DMG_PATH" "$DIST_DIR/appcast.xml" >/dev/null
else
  (
    cd "$DIST_DIR"
    /usr/bin/shasum -a 256 "${DMG_PATH:t}" > "${CHECKSUM_PATH:t}"
  )
  echo "Built a signed, unnotarized validation artifact. Use --notarize for public distribution." >&2
fi

printf '%s\n' "$APP_DIR" "$DMG_PATH"
