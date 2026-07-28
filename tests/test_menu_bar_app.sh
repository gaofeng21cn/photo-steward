#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$ROOT_DIR/app/PhotoCenterMenuBar"
SOURCE_DIR="$APP_DIR/Sources/PhotoCenterMenuBar"

[[ -d "$SOURCE_DIR" ]]
[[ -n "$(find "$SOURCE_DIR" -type f -name '*.swift' -print -quit)" ]]
plutil -lint "$APP_DIR/Info.plist" >/dev/null
[[ "$(plutil -extract CFBundleExecutable raw "$APP_DIR/Info.plist")" == "PhotoCenterMenuBar" ]]
[[ -n "$(plutil -extract NSNetworkVolumesUsageDescription raw "$APP_DIR/Info.plist")" ]]
[[ -n "$(plutil -extract NSPhotoLibraryUsageDescription raw "$APP_DIR/Info.plist")" ]]

# The menu bar remains a fast entry point; the auditable workflow lives in a window.
rg -Fq 'MenuBarExtra' "$SOURCE_DIR"
rg -Fq 'WindowGroup' "$SOURCE_DIR"
rg -Fq 'NavigationSplitView' "$SOURCE_DIR"
[[ -n "$(find "$SOURCE_DIR" -type f \( -iname '*control*.swift' -o -iname '*console*.swift' \) -print -quit)" ]]
[[ -n "$(find "$SOURCE_DIR" -type f -iname '*plan*.swift' -print -quit)" ]]

for label in "打开控制台" "生成计划" "待审计划" "执行 Apply"; do
  rg -Fq --glob '*.swift' "$label" "$SOURCE_DIR"
done

store_source="$SOURCE_DIR/Services/PhotoCenterStore.swift"
[[ "$(<"$store_source")" != *'probeNASAccess'* ]]
rg -Fq 'run(["preflight"]' "$store_source"
rg -Fq 'runtime/current/scripts/icloud-photo-sync' "$store_source"
rg -Fq 'PhotoStewardRuntimeController' "$SOURCE_DIR/Services/PhotoStewardRuntime.swift"
rg -Fq 'completeSetup' "$SOURCE_DIR/Views/SetupView.swift"

print "menu_bar_app: static console UX contract and plist valid"
