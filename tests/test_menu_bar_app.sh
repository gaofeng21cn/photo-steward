#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$ROOT_DIR/app/PhotoCenterMenuBar"
SOURCE_DIR="$APP_DIR/Sources/PhotoCenterMenuBar"

[[ -d "$SOURCE_DIR" ]]
[[ -n "$(find "$SOURCE_DIR" -type f -name '*.swift' -print -quit)" ]]
plutil -lint "$APP_DIR/Info.plist" >/dev/null
plutil -lint "$APP_DIR/PhotoSteward.entitlements" >/dev/null
[[ "$(plutil -extract CFBundleExecutable raw "$APP_DIR/Info.plist")" == "PhotoCenterMenuBar" ]]
[[ "$(/usr/libexec/PlistBuddy -c 'Print :com.apple.security.personal-information.photos-library' "$APP_DIR/PhotoSteward.entitlements")" == "true" ]]
[[ -n "$(plutil -extract NSNetworkVolumesUsageDescription raw "$APP_DIR/Info.plist")" ]]
[[ -n "$(plutil -extract NSPhotoLibraryUsageDescription raw "$APP_DIR/Info.plist")" ]]

# The menu bar remains a fast entry point; the auditable workflow lives in a window.
grep -rFq --include='*.swift' 'MenuBarExtra' "$SOURCE_DIR"
grep -Fq 'Window("Photo Steward", id: ControlCenterView.windowID)' "$SOURCE_DIR/main.swift"
! grep -Fq 'WindowGroup("Photo Steward"' "$SOURCE_DIR/main.swift"
grep -Fq 'MenuBarStatusIcon(health: store.health)' "$SOURCE_DIR/main.swift"
grep -Fq 'Image(systemName: "photo.on.rectangle.angled")' "$SOURCE_DIR/main.swift"
! grep -Fq 'Image(systemName: store.statusSymbol)' "$SOURCE_DIR/main.swift"
grep -rFq --include='*.swift' 'NavigationSplitView' "$SOURCE_DIR"
[[ -n "$(find "$SOURCE_DIR" -type f \( -iname '*control*.swift' -o -iname '*console*.swift' \) -print -quit)" ]]
[[ -n "$(find "$SOURCE_DIR" -type f -iname '*plan*.swift' -print -quit)" ]]

for label in "打开控制台" "生成新计划" "待审计划" "确认并执行此计划"; do
  grep -rFq --include='*.swift' "$label" "$SOURCE_DIR"
done
grep -Fq 'case settings' "$SOURCE_DIR/Views/ControlCenterView.swift"
grep -Fq 'ConfigurationView' "$SOURCE_DIR/Views/ControlCenterView.swift"
grep -Fq '保存并重新校验' "$SOURCE_DIR/Views/ConfigurationView.swift"
grep -Fq 'mirrorPhotosRoot' "$SOURCE_DIR/Services/PhotoStewardRuntime.swift"

store_source="$SOURCE_DIR/Services/PhotoCenterStore.swift"
[[ "$(<"$store_source")" != *'probeNASAccess'* ]]
grep -Fq 'run(["preflight"]' "$store_source"
grep -Fq 'runtime/current/scripts/icloud-photo-sync' "$store_source"
grep -Fq 'PhotoStewardRuntimeController' "$SOURCE_DIR/Services/PhotoStewardRuntime.swift"
grep -Fq 'completeSetup' "$SOURCE_DIR/Views/SetupView.swift"
grep -Fq 'discoverPhotosLibrary' "$SOURCE_DIR/Views/SetupView.swift"
grep -Fq '"--force"' "$SOURCE_DIR/Services/PhotoStewardRuntime.swift"

# Plan review uses one loader for thumbnails and detail sheets, including HEIC/ImageIO fallback.
grep -Fq 'PhotoPreviewLoader' "$SOURCE_DIR/Views/PlanReviewView.swift"
grep -Fq 'CGImageSourceCreateThumbnailAtIndex' "$SOURCE_DIR/Views/PlanReviewView.swift"
grep -Fq 'PHImageResultIsDegradedKey' "$SOURCE_DIR/Views/PlanReviewView.swift"
grep -Fq 'PHPhotoLibrary.authorizationStatus(for: .readWrite)' "$SOURCE_DIR/Views/PlanReviewView.swift"
grep -Fq 'PhotosAuthorizationCoordinator' "$SOURCE_DIR/Views/PlanReviewView.swift"
grep -Fq 'PHImageManager.default().cancelImageRequest' "$SOURCE_DIR/Views/PlanReviewView.swift"
grep -Fq '预览读取超时' "$SOURCE_DIR/Views/PlanReviewView.swift"
! grep -Fq 'if self.requestedMaxPixelSize > self.loadedMaxPixelSize' "$SOURCE_DIR/Views/PlanReviewView.swift"
grep -Fq '在 Finder 中查看' "$SOURCE_DIR/Views/PlanReviewView.swift"
grep -Fq '未找到已配置的 NAS 挂载点' "$SOURCE_DIR/Services/PhotoCenterStore.swift"
grep -Fq 'nas mount unavailable' "$SOURCE_DIR/Services/PhotoCenterStore.swift"
grep -Fq 'SPUStandardUpdaterController' "$SOURCE_DIR/Services/AppUpdater.swift"
grep -Fq 'updater.checkForUpdates()' "$SOURCE_DIR/Views/MenuBarPopover.swift"
grep -Fq 'updater.checkForUpdates()' "$SOURCE_DIR/Views/ConfigurationView.swift"

print "menu_bar_app: static console UX contract and plist valid"
