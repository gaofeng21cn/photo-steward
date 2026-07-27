#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
swift build --package-path "$ROOT_DIR/app/PhotoCenterMenuBar" -c release >/dev/null
[[ -x "$ROOT_DIR/app/PhotoCenterMenuBar/.build/release/PhotoCenterMenuBar" ]]
plutil -lint "$ROOT_DIR/app/PhotoCenterMenuBar/Info.plist" >/dev/null
[[ "$(plutil -extract CFBundleExecutable raw "$ROOT_DIR/app/PhotoCenterMenuBar/Info.plist")" == "PhotoCenterMenuBar" ]]
[[ -n "$(plutil -extract NSNetworkVolumesUsageDescription raw "$ROOT_DIR/app/PhotoCenterMenuBar/Info.plist")" ]]
rg -q -- "--run-job" "$ROOT_DIR/app/PhotoCenterMenuBar/Sources/PhotoCenterMenuBar/main.swift"
rg -Fq 'run(["preflight"], timeoutSeconds: 15)' "$ROOT_DIR/app/PhotoCenterMenuBar/Sources/PhotoCenterMenuBar/main.swift"
print "menu_bar_app: SwiftUI release build and plist valid"
