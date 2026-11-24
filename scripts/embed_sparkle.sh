#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_PATH=""
SIGNING_IDENTITY="-"
ARTIFACTS_DIR=""
ARCHS=""
EXPECTED_FEED_URL="https://github.com/gaofeng21cn/photo-steward/releases/latest/download/appcast.xml"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)
      APP_PATH="$2"
      shift 2
      ;;
    --signing-identity)
      SIGNING_IDENTITY="$2"
      shift 2
      ;;
    --artifacts-dir)
      ARTIFACTS_DIR="$2"
      shift 2
      ;;
    --archs)
      ARCHS="$2"
      shift 2
      ;;
    --expected-feed-url)
      EXPECTED_FEED_URL="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$APP_PATH" || ! -d "$APP_PATH" ]]; then
  echo "App bundle not found: ${APP_PATH:-<empty>}" >&2
  exit 1
fi

if [[ -z "$ARTIFACTS_DIR" ]]; then
  for candidate in \
    "$ROOT_DIR/app/PhotoCenterMenuBar/.build/artifacts" \
    "$ROOT_DIR/.build/artifacts"
  do
    if [[ -d "$candidate" ]]; then
      ARTIFACTS_DIR="$candidate"
      break
    fi
  done
fi

if [[ -z "$ARTIFACTS_DIR" || ! -d "$ARTIFACTS_DIR" ]]; then
  echo "Sparkle artifacts directory not found." >&2
  exit 1
fi

SHARED_EMBED_SCRIPT="${OPL_MACOS_SPARKLE_SCRIPTS_DIR:-}/embed-and-sign-sparkle.sh"
if [[ -n "${OPL_MACOS_SPARKLE_SCRIPTS_DIR:-}" && -x "$SHARED_EMBED_SCRIPT" ]]; then
  typeset -a embed_args
  embed_args=(
    --app "$APP_PATH"
    --signing-identity "$SIGNING_IDENTITY"
    --artifacts-dir "$ARTIFACTS_DIR"
    --expected-feed-url "$EXPECTED_FEED_URL"
  )
  if [[ -n "$ARCHS" ]]; then
    embed_args+=(--archs "$ARCHS")
  fi
  "$SHARED_EMBED_SCRIPT" "${embed_args[@]}"
  exit 0
fi

SPARKLE_FRAMEWORK_SRC="$ARTIFACTS_DIR/sparkle/Sparkle/Sparkle.xcframework/macos-arm64_x86_64/Sparkle.framework"
if [[ ! -d "$SPARKLE_FRAMEWORK_SRC" ]]; then
  SPARKLE_FRAMEWORK_SRC="$(/usr/bin/find "$ARTIFACTS_DIR" -path '*/Sparkle.xcframework/macos-arm64_x86_64/Sparkle.framework' -type d -print -quit 2>/dev/null || true)"
fi
if [[ -z "$SPARKLE_FRAMEWORK_SRC" || ! -d "$SPARKLE_FRAMEWORK_SRC" ]]; then
  echo "Sparkle.framework not found under $ARTIFACTS_DIR." >&2
  exit 1
fi

PLIST_PATH="$APP_PATH/Contents/Info.plist"
/usr/bin/plutil -lint "$PLIST_PATH" >/dev/null
FEED_URL="$(/usr/bin/plutil -extract SUFeedURL raw "$PLIST_PATH")"
PUBLIC_ED_KEY="$(/usr/bin/plutil -extract SUPublicEDKey raw "$PLIST_PATH")"
AUTO_CHECKS="$(/usr/bin/plutil -extract SUEnableAutomaticChecks raw "$PLIST_PATH")"

if [[ "$FEED_URL" != "$EXPECTED_FEED_URL" ]]; then
  echo "Expected SUFeedURL $EXPECTED_FEED_URL, got ${FEED_URL:-<empty>}." >&2
  exit 1
fi
if [[ "$AUTO_CHECKS" != "true" ]]; then
  echo "Expected SUEnableAutomaticChecks=true, got ${AUTO_CHECKS:-<empty>}." >&2
  exit 1
fi
/usr/bin/python3 - "$PUBLIC_ED_KEY" <<'PY'
import base64
import sys

raw = base64.b64decode(sys.argv[1], validate=True)
if len(raw) != 32:
    raise SystemExit(f"Expected 32-byte Ed25519 public key, got {len(raw)} bytes")
PY

FRAMEWORKS_DIR="$APP_PATH/Contents/Frameworks"
SPARKLE_DEST="$FRAMEWORKS_DIR/Sparkle.framework"
SPARKLE_VER="$SPARKLE_DEST/Versions/B"
/bin/mkdir -p "$FRAMEWORKS_DIR"
/bin/rm -rf "$SPARKLE_DEST"
/usr/bin/ditto "$SPARKLE_FRAMEWORK_SRC" "$SPARKLE_DEST"

if [[ -n "$ARCHS" ]]; then
  for ARCH in ${=ARCHS}; do
    /usr/bin/lipo "$SPARKLE_VER/Sparkle" -verify_arch "$ARCH"
  done
fi

typeset -a sign_args
sign_args=(--force --sign "$SIGNING_IDENTITY")
if [[ "$SIGNING_IDENTITY" != "-" ]]; then
  sign_args+=(--options runtime --timestamp)
fi

/usr/bin/codesign "${sign_args[@]}" "$SPARKLE_VER/XPCServices/Installer.xpc"
/usr/bin/codesign "${sign_args[@]}" --preserve-metadata=entitlements "$SPARKLE_VER/XPCServices/Downloader.xpc"
/usr/bin/codesign "${sign_args[@]}" "$SPARKLE_VER/Autoupdate"
/usr/bin/codesign "${sign_args[@]}" "$SPARKLE_VER/Updater.app"
/usr/bin/codesign "${sign_args[@]}" "$SPARKLE_DEST"
