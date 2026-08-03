#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGE_SCRIPT="$ROOT_DIR/scripts/package_release.sh"
FRESH_CLONE_SCRIPT="$ROOT_DIR/scripts/verify_fresh_clone.sh"

[[ -x "$PACKAGE_SCRIPT" ]]
[[ -x "$FRESH_CLONE_SCRIPT" ]]
[[ -x "$ROOT_DIR/scripts/stage_runtime.sh" ]]
[[ -x "$ROOT_DIR/scripts/sign_runtime.sh" ]]
[[ -f "$ROOT_DIR/app/PhotoCenterMenuBar/PhotoSteward.entitlements" ]]
[[ -f "$ROOT_DIR/app/PhotoCenterMenuBar/Resources/PhotoSteward.png" ]]
[[ -f "$ROOT_DIR/app/PhotoCenterMenuBar/Resources/PhotoSteward.icns" ]]
zsh -n "$PACKAGE_SCRIPT" "$FRESH_CLONE_SCRIPT"
plutil -extract CFBundleIconFile raw -o - \
  "$ROOT_DIR/app/PhotoCenterMenuBar/Info.plist" | rg -Fxq 'PhotoSteward.icns'
rg -Fq -- '--notarize' "$PACKAGE_SCRIPT"
rg -Fq -- 'Developer ID Application' "$PACKAGE_SCRIPT"
rg -Fq -- 'lipo' "$PACKAGE_SCRIPT"
rg -Fq -- 'xcrun notarytool submit' "$PACKAGE_SCRIPT"
rg -Fq -- 'PhotoStewardRuntime' "$PACKAGE_SCRIPT"
rg -Fq -- 'Python3.framework' "$ROOT_DIR/scripts/stage_runtime.sh"
rg -Fq -- 'stage_runtime.sh' "$PACKAGE_SCRIPT"
rg -Fq -- 'sign_runtime.sh' "$PACKAGE_SCRIPT"
rg -Fq -- 'PhotoSteward.entitlements' "$PACKAGE_SCRIPT"
rg -Fq -- '--entitlements "$ENTITLEMENTS"' "$PACKAGE_SCRIPT"
rg -Fq -- '--entitlements "$ENTITLEMENTS"' "$ROOT_DIR/scripts/install_menu_bar_app.sh"
rg -Fq -- '--entitlements "$ENTITLEMENTS"' "$ROOT_DIR/scripts/sign_runtime.sh"
rg -Fq -- '"$SIGNING_IDENTITY" != "-"' "$ROOT_DIR/scripts/sign_runtime.sh"
[[ "$(rg -Fc -- 'scripts/sign_runtime.sh' "$ROOT_DIR/scripts/install_menu_bar_app.sh")" == "2" ]]
! rg -Fq -- '--deep' "$ROOT_DIR/scripts/install_menu_bar_app.sh"
rg -Fq -- 'fresh clone validation passed' "$FRESH_CLONE_SCRIPT"

print "release_packaging: icon and distribution gates present"
