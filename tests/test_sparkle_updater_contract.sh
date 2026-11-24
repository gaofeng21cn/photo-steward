#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGE_DIR="$ROOT_DIR/app/PhotoCenterMenuBar"
INFO_PLIST="$PACKAGE_DIR/Info.plist"
EXPECTED_FEED_URL="https://github.com/gaofeng21cn/photo-steward/releases/latest/download/appcast.xml"

# 1. Package.swift must wire Sparkle 2 into PhotoCenterMenuBar with framework rpath.
grep -Fq 'https://github.com/sparkle-project/Sparkle' "$PACKAGE_DIR/Package.swift"
grep -Fq '.product(name: "Sparkle", package: "Sparkle")' "$PACKAGE_DIR/Package.swift"
grep -Fq '@executable_path/../Frameworks' "$PACKAGE_DIR/Package.swift"

# 2. Info.plist must declare valid Sparkle feed, 32-byte Ed25519 key, monotonic build, and automatic checks.
/usr/bin/plutil -lint "$INFO_PLIST" >/dev/null
ACTUAL_FEED_URL="$(/usr/bin/plutil -extract SUFeedURL raw "$INFO_PLIST")"
ACTUAL_PUBLIC_KEY="$(/usr/bin/plutil -extract SUPublicEDKey raw "$INFO_PLIST")"
ACTUAL_AUTO_CHECKS="$(/usr/bin/plutil -extract SUEnableAutomaticChecks raw "$INFO_PLIST")"
ACTUAL_AUTO_UPDATE="$(/usr/bin/plutil -extract SUAutomaticallyUpdate raw "$INFO_PLIST")"
ACTUAL_VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw "$INFO_PLIST")"
ACTUAL_BUILD="$(/usr/bin/plutil -extract CFBundleVersion raw "$INFO_PLIST")"
ACTUAL_MIN_SYS="$(/usr/bin/plutil -extract LSMinimumSystemVersion raw "$INFO_PLIST")"

if [[ "$ACTUAL_FEED_URL" != "$EXPECTED_FEED_URL" ]]; then
  echo "Unexpected SUFeedURL in Info.plist: ${ACTUAL_FEED_URL:-none}" >&2
  exit 1
fi
if [[ "$ACTUAL_AUTO_CHECKS" != "true" ]]; then
  echo "Expected SUEnableAutomaticChecks=true, got ${ACTUAL_AUTO_CHECKS:-none}" >&2
  exit 1
fi
if [[ "$ACTUAL_AUTO_UPDATE" != "false" ]]; then
  echo "Expected SUAutomaticallyUpdate=false, got ${ACTUAL_AUTO_UPDATE:-none}" >&2
  exit 1
fi
if [[ ! "$ACTUAL_BUILD" =~ ^[1-9][0-9]*$ ]]; then
  echo "Expected positive monotonic integer CFBundleVersion, got ${ACTUAL_BUILD:-none}" >&2
  exit 1
fi
if [[ -z "$ACTUAL_MIN_SYS" ]]; then
  echo "LSMinimumSystemVersion is required for Sparkle appcast generation." >&2
  exit 1
fi
/usr/bin/python3 - "$ACTUAL_PUBLIC_KEY" <<'PY'
import base64
import sys

raw = base64.b64decode(sys.argv[1], validate=True)
if len(raw) != 32:
    raise SystemExit(f"Expected 32-byte Ed25519 public key, got {len(raw)} bytes")
PY

# 3. AppUpdater and UI must expose native Sparkle in-app updates.
grep -Fq 'SPUStandardUpdaterController' "$PACKAGE_DIR/Sources/PhotoCenterMenuBar/Services/AppUpdater.swift"
grep -Fq 'updater.checkForUpdates()' "$PACKAGE_DIR/Sources/PhotoCenterMenuBar/main.swift"
grep -Fq 'updater.checkForUpdates()' "$PACKAGE_DIR/Sources/PhotoCenterMenuBar/Views/MenuBarPopover.swift"
grep -Fq 'updater.checkForUpdates()' "$PACKAGE_DIR/Sources/PhotoCenterMenuBar/Views/ConfigurationView.swift"

# 4. Packaging and release workflow must embed/sign Sparkle inside-out and publish signed appcast.xml.
grep -Fq 'Installer.xpc' "$ROOT_DIR/scripts/embed_sparkle.sh"
grep -Fq 'Downloader.xpc' "$ROOT_DIR/scripts/embed_sparkle.sh"
grep -Fq 'Autoupdate' "$ROOT_DIR/scripts/embed_sparkle.sh"
grep -Fq 'Updater.app' "$ROOT_DIR/scripts/embed_sparkle.sh"
grep -Fq 'embed_sparkle.sh' "$ROOT_DIR/scripts/package_release.sh"
grep -Fq 'embed_sparkle.sh' "$ROOT_DIR/scripts/install_menu_bar_app.sh"
grep -Fq 'reusable-macos-sparkle-release.yml' "$ROOT_DIR/.github/workflows/release.yml"
grep -Fq 'appcast.xml' "$ROOT_DIR/.github/workflows/release.yml"

# 5. End-to-end appcast generation and fail-closed verification with an ephemeral Ed25519 key.
SPARKLE_GENERATE=""
for candidate in \
  "$PACKAGE_DIR/.build/artifacts" \
  "$ROOT_DIR/.build/artifacts" \
  "$ROOT_DIR/tmp/photo-steward-release-build/arm64/artifacts"
do
  if [[ -x "$candidate/sparkle/Sparkle/bin/generate_appcast" ]]; then
    SPARKLE_GENERATE="$candidate/sparkle/Sparkle/bin/generate_appcast"
    break
  fi
done
if [[ -z "$SPARKLE_GENERATE" ]]; then
  echo "Sparkle CLI tools missing under app/PhotoCenterMenuBar/.build/artifacts; run swift build first." >&2
  exit 1
fi

TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/photo-steward-sparkle-contract.XXXXXX")"
cleanup() {
  rm -rf "${TEMP_ROOT:?}"
}
trap cleanup EXIT INT TERM

EPHEMERAL_KEYS="$(/usr/bin/swift -e 'import CryptoKit; import Foundation; let key = Curve25519.Signing.PrivateKey(); print(key.rawRepresentation.base64EncodedString()); print(key.publicKey.rawRepresentation.base64EncodedString())')"
EPHEMERAL_PRIV_KEY="$(printf '%s\n' "$EPHEMERAL_KEYS" | sed -n '1p')"
EPHEMERAL_PUB_KEY="$(printf '%s\n' "$EPHEMERAL_KEYS" | sed -n '2p')"

STAGING="$TEMP_ROOT/staging"
FAKE_APP="$STAGING/Photo Steward.app"
mkdir -p "$FAKE_APP/Contents/MacOS"
cp "$INFO_PLIST" "$FAKE_APP/Contents/Info.plist"
/usr/bin/plutil -replace SUPublicEDKey -string "$EPHEMERAL_PUB_KEY" "$FAKE_APP/Contents/Info.plist"
cp /usr/bin/true "$FAKE_APP/Contents/MacOS/PhotoCenterMenuBar"
chmod +x "$FAKE_APP/Contents/MacOS/PhotoCenterMenuBar"
/usr/bin/codesign --force --sign - "$FAKE_APP" >/dev/null 2>&1

FAKE_DMG="$TEMP_ROOT/Photo-Steward.dmg"
/usr/bin/hdiutil create \
  -volname "Photo Steward" \
  -srcfolder "$STAGING" \
  -format UDZO \
  -ov \
  "$FAKE_DMG" >/dev/null

OUT_APPCAST="$TEMP_ROOT/appcast.xml"

SPARKLE_ED25519_PRIVATE_KEY="$EPHEMERAL_PRIV_KEY" \
PHOTO_STEWARD_RELEASE_TAG="v$ACTUAL_VERSION" \
PHOTO_STEWARD_APP_PATH="$FAKE_APP" \
PHOTO_STEWARD_REQUIRE_SPARKLE_KEY_ENV=1 \
  "$ROOT_DIR/scripts/generate_appcast.sh" "$FAKE_DMG" "$OUT_APPCAST" >/dev/null

[[ -s "$OUT_APPCAST" ]]
grep -Fq "<sparkle:version>$ACTUAL_BUILD</sparkle:version>" "$OUT_APPCAST"
grep -Fq "<sparkle:shortVersionString>$ACTUAL_VERSION</sparkle:shortVersionString>" "$OUT_APPCAST"
grep -Fq 'sparkle:edSignature="' "$OUT_APPCAST"

# Negative check: mismatched private key must fail closed rather than emitting an appcast.
WRONG_PRIV_KEY="$(/usr/bin/openssl rand -base64 32)"
if SPARKLE_ED25519_PRIVATE_KEY="$WRONG_PRIV_KEY" \
  PHOTO_STEWARD_RELEASE_TAG="v$ACTUAL_VERSION" \
  PHOTO_STEWARD_APP_PATH="$FAKE_APP" \
  PHOTO_STEWARD_REQUIRE_SPARKLE_KEY_ENV=1 \
  "$ROOT_DIR/scripts/generate_appcast.sh" "$FAKE_DMG" "$TEMP_ROOT/wrong-appcast.xml" >/dev/null 2>&1
then
  echo "generate_appcast.sh unexpectedly accepted a mismatched Ed25519 key." >&2
  exit 1
fi

echo "Verified Photo Steward Sparkle 2 updater contract and signed appcast generation for v$ACTUAL_VERSION ($ACTUAL_BUILD)."
