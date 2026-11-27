#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGE_SCRIPT="$ROOT_DIR/scripts/package_release.sh"
FRESH_CLONE_SCRIPT="$ROOT_DIR/scripts/verify_fresh_clone.sh"

[[ -x "$PACKAGE_SCRIPT" ]]
[[ -x "$FRESH_CLONE_SCRIPT" ]]
[[ -x "$ROOT_DIR/scripts/stage_runtime.sh" ]]
[[ -x "$ROOT_DIR/scripts/sign_runtime.sh" ]]
[[ -x "$ROOT_DIR/scripts/embed_sparkle.sh" ]]
[[ -x "$ROOT_DIR/scripts/generate_appcast.sh" ]]
[[ -f "$ROOT_DIR/.github/workflows/release.yml" ]]
[[ -f "$ROOT_DIR/app/PhotoCenterMenuBar/PhotoSteward.entitlements" ]]
[[ -f "$ROOT_DIR/app/PhotoCenterMenuBar/Resources/PhotoSteward.png" ]]
[[ -f "$ROOT_DIR/app/PhotoCenterMenuBar/Resources/PhotoSteward.icns" ]]
zsh -n "$PACKAGE_SCRIPT" "$FRESH_CLONE_SCRIPT" "$ROOT_DIR/scripts/embed_sparkle.sh" "$ROOT_DIR/scripts/generate_appcast.sh"
plutil -extract CFBundleIconFile raw -o - \
  "$ROOT_DIR/app/PhotoCenterMenuBar/Info.plist" | grep -Fxq 'PhotoSteward.icns'
grep -Fq -- '--notarize' "$PACKAGE_SCRIPT"
grep -Fq -- '--app-only' "$PACKAGE_SCRIPT"
grep -Fq -- 'Developer ID Application' "$PACKAGE_SCRIPT"
grep -Fq -- 'lipo' "$PACKAGE_SCRIPT"
grep -Fq -- '/usr/bin/strip -S "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"' "$PACKAGE_SCRIPT"
grep -Fq -- 'xcrun notarytool submit' "$PACKAGE_SCRIPT"
grep -Fq -- 'PhotoStewardRuntime' "$PACKAGE_SCRIPT"
grep -Fq -- 'embed_sparkle.sh' "$PACKAGE_SCRIPT"
grep -Fq -- 'prepare_python_runtime.py' "$ROOT_DIR/scripts/stage_runtime.sh"
grep -Fq -- 'stage_runtime.sh' "$PACKAGE_SCRIPT"
grep -Fq -- 'sign_runtime.sh' "$PACKAGE_SCRIPT"
grep -Fq -- 'PhotoSteward.entitlements' "$PACKAGE_SCRIPT"
grep -Fq -- '--entitlements "$ENTITLEMENTS"' "$PACKAGE_SCRIPT"
grep -Fq -- '--entitlements "$ENTITLEMENTS"' "$ROOT_DIR/scripts/install_menu_bar_app.sh"
grep -Fq -- '--entitlements "$ENTITLEMENTS"' "$ROOT_DIR/scripts/sign_runtime.sh"
grep -Fq -- '"$SIGNING_IDENTITY" != "-"' "$ROOT_DIR/scripts/sign_runtime.sh"
[[ "$(grep -Fc -- 'scripts/sign_runtime.sh' "$ROOT_DIR/scripts/install_menu_bar_app.sh")" == "2" ]]
! grep -Fq -- '--deep' "$ROOT_DIR/scripts/install_menu_bar_app.sh"
grep -Fq -- 'fresh clone validation passed' "$FRESH_CLONE_SCRIPT"
grep -Fq -- 'CFBundleShortVersionString' "$ROOT_DIR/.github/workflows/release.yml"
grep -Fq -- 'reusable-macos-sparkle-release.yml' "$ROOT_DIR/.github/workflows/release.yml"
grep -Fq -- 'appcast.xml' "$ROOT_DIR/.github/workflows/release.yml"
grep -Fq -- 'gh release create "$GITHUB_REF_NAME" --verify-tag' "$ROOT_DIR/.github/workflows/release.yml"
grep -Fq -- 'github.token' "$ROOT_DIR/.github/workflows/release.yml"

lipo_line="$(grep -n -F '/usr/bin/lipo "${binaries[@]}" -create' "$PACKAGE_SCRIPT" | cut -d: -f1)"
strip_line="$(grep -n -F '/usr/bin/strip -S "$APP_DIR/Contents/MacOS/PhotoCenterMenuBar"' "$PACKAGE_SCRIPT" | cut -d: -f1)"
codesign_line="$(grep -n -F '/usr/bin/codesign \' "$PACKAGE_SCRIPT" | cut -d: -f1)"
(( lipo_line < strip_line && strip_line < codesign_line ))

print "release_packaging: icon and distribution gates present"
