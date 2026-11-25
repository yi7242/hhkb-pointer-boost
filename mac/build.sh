#!/bin/bash
# Build "HHKB Pointer Boost.app" with the Xcode Command Line Tools.
#   ./build.sh            -> build/HHKB Pointer Boost.app
#   ./build.sh --install  -> also copy it to ~/Applications and start it
set -euo pipefail
cd "$(dirname "$0")"

APP="build/HHKB Pointer Boost.app"
ARCH="$(uname -m)"
ICONSET="build/AppIcon.iconset"

if ! command -v swiftc >/dev/null 2>&1; then
  echo "swiftc が見つかりません。先に xcode-select --install を実行してください。" >&2
  exit 1
fi

rm -rf "$APP" "$ICONSET"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$ICONSET"

swiftc -O -target "${ARCH}-apple-macos13.0" \
  -o "$APP/Contents/MacOS/HHKBPointerBoost" main.swift
cp Info.plist "$APP/Contents/Info.plist"

for size in 16 32 128 256 512; do
  sips -z "$size" "$size" AppIcon.png --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" AppIcon.png --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
rm -rf "$ICONSET"

# Ad-hoc signature so macOS can keep the Input Monitoring permission for this build.
codesign --force --sign - "$APP"
echo "built: $(pwd)/$APP"

if [[ "${1:-}" == "--install" ]]; then
  DEST="$HOME/Applications/HHKB Pointer Boost.app"
  mkdir -p "$HOME/Applications"
  osascript -e 'tell application id "local.hhkbpointerboost" to quit' >/dev/null 2>&1 || true
  sleep 1
  rm -rf "$DEST"
  cp -R "$APP" "$DEST"
  open "$DEST"
  echo "installed: $DEST"
fi
