#!/usr/bin/env bash
# make-ipa.sh — produce a signed RalphVC.ipa for Ad-Hoc OTA distribution.
#
# Output: build/RalphVC.ipa + build/RalphVC.dSYM.zip
#
# Requirements:
#   - macOS with Xcode 15+
#   - Apple Developer Program membership (paid, $99/yr)
#   - An Ad-Hoc provisioning profile listing your iPhone's UDID
#     (developer.apple.com → Certificates, IDs & Profiles → Profiles → Ad Hoc)
#
# Authored by Chase Eddies <source@distillative.ai>.

set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

usage() {
  cat <<'USAGE'
Usage: ./distribution/make-ipa.sh --team-id ABCDE12345 [options]

Required:
  --team-id ID            Your Apple Developer team id

Optional:
  --bundle-id ID          Override the bundle id (default: com.distillative.ralphvc)
  --version X.Y.Z         Marketing version (default: 0.1.0)
  --build N               Build number (default: timestamp)
  --output DIR            Build output dir (default: build/)
USAGE
}

TEAM_ID=""
BUNDLE_ID="com.distillative.ralphvc"
VERSION="0.1.0"
BUILD_NO="$(date +%s)"
OUT="build"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --team-id)   TEAM_ID="$2";   shift 2 ;;
    --bundle-id) BUNDLE_ID="$2"; shift 2 ;;
    --version)   VERSION="$2";   shift 2 ;;
    --build)     BUILD_NO="$2";  shift 2 ;;
    --output)    OUT="$2";       shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *)           echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

[[ -z "$TEAM_ID" ]] && { echo "missing --team-id" >&2; usage; exit 2; }

# Generate the .xcodeproj if needed.
if [[ ! -d ios-app/RalphVC.xcodeproj ]]; then
  command -v xcodegen >/dev/null || { echo "install xcodegen: brew install xcodegen" >&2; exit 2; }
  ( cd ios-app && DEVELOPMENT_TEAM="$TEAM_ID" xcodegen generate )
fi

mkdir -p "$OUT"
ARCHIVE="$OUT/RalphVC.xcarchive"

echo "[1/3] archiving"
xcodebuild \
  -project ios-app/RalphVC.xcodeproj \
  -scheme RalphVC \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath "$ARCHIVE" \
  DEVELOPMENT_TEAM="$TEAM_ID" \
  CODE_SIGN_STYLE=Automatic \
  PRODUCT_BUNDLE_IDENTIFIER="$BUNDLE_ID" \
  MARKETING_VERSION="$VERSION" \
  CURRENT_PROJECT_VERSION="$BUILD_NO" \
  archive

echo "[2/3] exporting Ad-Hoc .ipa"
EXPORT_PLIST="$OUT/ExportOptions.plist"
cat > "$EXPORT_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>method</key>             <string>ad-hoc</string>
  <key>signingStyle</key>       <string>automatic</string>
  <key>teamID</key>             <string>${TEAM_ID}</string>
  <key>compileBitcode</key>     <false/>
  <key>thinning</key>           <string>&lt;none&gt;</string>
  <key>uploadSymbols</key>      <false/>
  <key>destination</key>        <string>export</string>
</dict>
</plist>
EOF

xcodebuild \
  -exportArchive \
  -archivePath "$ARCHIVE" \
  -exportPath  "$OUT/export" \
  -exportOptionsPlist "$EXPORT_PLIST"

cp "$OUT/export/RalphVC.ipa" "$OUT/RalphVC.ipa"

echo "[3/3] writing OTA manifest template"
python3 distribution/render_install_page.py \
  --bundle-id "$BUNDLE_ID" \
  --version   "$VERSION" \
  --output    "$OUT"

echo
echo "done."
echo "  ipa:           $OUT/RalphVC.ipa"
echo "  install page:  $OUT/install.html"
echo "  manifest:      $OUT/manifest.plist (will need its ipa-url rewritten on host.sh)"
echo
echo "next: ./distribution/host.sh --provider <pages|netlify|s3> $OUT"
