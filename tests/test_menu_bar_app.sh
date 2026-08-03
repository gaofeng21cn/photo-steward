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
rg -Fq 'Window("Photo Steward", id: ControlCenterView.windowID)' "$SOURCE_DIR/main.swift"
! rg -Fq 'WindowGroup("Photo Steward"' "$SOURCE_DIR/main.swift"
rg -Fq 'NavigationSplitView' "$SOURCE_DIR"
[[ -n "$(find "$SOURCE_DIR" -type f \( -iname '*control*.swift' -o -iname '*console*.swift' \) -print -quit)" ]]
[[ -n "$(find "$SOURCE_DIR" -type f -iname '*plan*.swift' -print -quit)" ]]

for label in "打开控制台" "生成新计划" "待审计划" "确认并执行此计划"; do
  rg -Fq --glob '*.swift' "$label" "$SOURCE_DIR"
done
rg -Fq 'case settings' "$SOURCE_DIR/Views/ControlCenterView.swift"
rg -Fq 'ConfigurationView' "$SOURCE_DIR/Views/ControlCenterView.swift"
rg -Fq '保存并重新校验' "$SOURCE_DIR/Views/ConfigurationView.swift"
rg -Fq 'mirrorPhotosRoot' "$SOURCE_DIR/Services/PhotoStewardRuntime.swift"

store_source="$SOURCE_DIR/Services/PhotoCenterStore.swift"
[[ "$(<"$store_source")" != *'probeNASAccess'* ]]
rg -Fq 'run(["preflight"]' "$store_source"
rg -Fq 'runtime/current/scripts/icloud-photo-sync' "$store_source"
rg -Fq 'PhotoStewardRuntimeController' "$SOURCE_DIR/Services/PhotoStewardRuntime.swift"
rg -Fq 'completeSetup' "$SOURCE_DIR/Views/SetupView.swift"
rg -Fq 'discoverPhotosLibrary' "$SOURCE_DIR/Views/SetupView.swift"
rg -Fq '"--force"' "$SOURCE_DIR/Services/PhotoStewardRuntime.swift"

# Plan review uses one loader for thumbnails and detail sheets, including HEIC/ImageIO fallback.
rg -Fq 'PhotoPreviewLoader' "$SOURCE_DIR/Views/PlanReviewView.swift"
rg -Fq 'CGImageSourceCreateThumbnailAtIndex' "$SOURCE_DIR/Views/PlanReviewView.swift"
rg -Fq 'PHImageResultIsDegradedKey' "$SOURCE_DIR/Views/PlanReviewView.swift"
rg -Fq 'PHPhotoLibrary.authorizationStatus(for: .readWrite)' "$SOURCE_DIR/Views/PlanReviewView.swift"
rg -Fq 'PhotosAuthorizationCoordinator' "$SOURCE_DIR/Views/PlanReviewView.swift"
rg -Fq 'PHImageManager.default().cancelImageRequest' "$SOURCE_DIR/Views/PlanReviewView.swift"
rg -Fq '预览读取超时' "$SOURCE_DIR/Views/PlanReviewView.swift"
! rg -Fq 'if self.requestedMaxPixelSize > self.loadedMaxPixelSize' "$SOURCE_DIR/Views/PlanReviewView.swift"
rg -Fq '在 Finder 中查看' "$SOURCE_DIR/Views/PlanReviewView.swift"
rg -Fq '未找到 NAS 挂载点' "$SOURCE_DIR/Services/PhotoCenterStore.swift"
rg -Fq 'nas mount unavailable' "$SOURCE_DIR/Services/PhotoCenterStore.swift"

print "menu_bar_app: static console UX contract and plist valid"
