#!/usr/bin/env bash
# testflight.sh — build, sign, and upload RalphVC.ipa to App Store Connect
# for TestFlight distribution.
#
# This is the third install path (alongside web/ PWA and distribution/
# Ad-Hoc OTA): Apple hosts the download and the install experience for
# testers, so there's no HTTPS hosting, no UDID registration, and the
# tester just taps a link and installs from the TestFlight app.
#
# Output: build/RalphVC.ipa + build/RalphVC.xcarchive, uploaded to
# App Store Connect.
#
# Requirements:
#   - macOS with Xcode 15+
#   - Apple Developer Program membership (paid, $99/yr)
#   - An App Store Connect app record already created for the bundle id
#     (App Store Connect → My Apps → + → New App)
#   - Either:
#       xcrun notarytool  (Xcode 13+, preferred — needs an App Store
#                           Connect API key: --apple-id is ignored)
#     or
#       xcrun altool      (older Xcode — needs Apple ID + an
#                           app-specific password, NOT your account
#                           password: https://appleid.apple.com →
#                           Sign-In and Security → App-Specific Passwords)
#   - Credentials via flags or env vars:
#       APPLE_ID               your Apple ID email (altool path)
#       APP_SPECIFIC_PASSWORD  app-specific password (altool path)
#       TEAM_ID                your Apple Developer team id
#
# Authored by Chase Eddies <source@distillative.ai>.
# Coding assistant: Claude Code Cloud.

set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

usage() {
  cat <<'USAGE'
Usage: ./distribution/testflight.sh --team-id ABCDE12345 [options]

Required:
  --team-id ID            Your Apple Developer team id

Optional (Apple ID / altool upload path):
  --apple-id EMAIL         Apple ID email used to sign in to App Store
                            Connect (or set APPLE_ID). Ignored if
                            xcrun notarytool is available and
                            --api-key-id / --api-issuer-id are set.

Optional (build metadata):
  --bundle-id ID          Override the bundle id (default: com.distillative.ralphvc)
  --version X.Y.Z         Marketing version (default: 0.1.0)
  --build N               Build number (default: timestamp)
  --output DIR            Build output dir (default: build/)

Environment variables (in place of the above / for the password):
  APPLE_ID                Apple ID email (same as --apple-id)
  APP_SPECIFIC_PASSWORD   App-specific password for APPLE_ID
                          (https://appleid.apple.com → Sign-In and
                          Security → App-Specific Passwords)
  TEAM_ID                 Apple Developer team id (same as --team-id)

Examples:
  # altool path (Apple ID + app-specific password)
  export APPLE_ID=you@example.com
  export APP_SPECIFIC_PASSWORD=abcd-efgh-ijkl-mnop
  ./distribution/testflight.sh --team-id ABCDE12345

  # notarytool path (App Store Connect API key, no password needed)
  ./distribution/testflight.sh --team-id ABCDE12345 \
      --api-key-id XXXXXXXXXX --api-issuer-id 11111111-2222-3333-4444-555555555555
USAGE
}

TEAM_ID="${TEAM_ID:-}"
APPLE_ID="${APPLE_ID:-}"
APP_SPECIFIC_PASSWORD="${APP_SPECIFIC_PASSWORD:-}"
API_KEY_ID=""
API_ISSUER_ID=""
BUNDLE_ID="com.distillative.ralphvc"
VERSION="0.1.0"
BUILD_NO="$(date +%s)"
OUT="build"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --team-id)        TEAM_ID="$2";        shift 2 ;;
    --apple-id)        APPLE_ID="$2";        shift 2 ;;
    --bundle-id)       BUNDLE_ID="$2";       shift 2 ;;
    --version)         VERSION="$2";         shift 2 ;;
    --build)           BUILD_NO="$2";        shift 2 ;;
    --output)          OUT="$2";             shift 2 ;;
    --api-key-id)      API_KEY_ID="$2";      shift 2 ;;
    --api-issuer-id)   API_ISSUER_ID="$2";   shift 2 ;;
    -h|--help)         usage; exit 0 ;;
    *)                 echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

[[ -z "$TEAM_ID" ]] && { echo "missing --team-id (or set TEAM_ID)" >&2; usage; exit 2; }

# ----- 1. prereqs ------------------------------------------------------------

echo "[1/5] checking prerequisites"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "this script must run on macOS — Xcode is required to build iOS apps." >&2
  exit 2
fi

command -v xcrun      >/dev/null || { echo "xcrun not found. Install Xcode 15+." >&2; exit 2; }
command -v xcodebuild >/dev/null || { echo "xcodebuild not found. Install Xcode 15+." >&2; exit 2; }

# Xcode 15+ check (best-effort: parse `xcodebuild -version`).
XCODE_MAJOR="$(xcodebuild -version 2>/dev/null | awk '/^Xcode/ {split($2,v,"."); print v[1]; exit}')"
if [[ -n "$XCODE_MAJOR" && "$XCODE_MAJOR" -lt 15 ]]; then
  echo "Xcode 15+ required for App Store distribution (found Xcode $XCODE_MAJOR)." >&2
  exit 2
fi

# Decide the upload tool: prefer notarytool (modern, API-key based) when the
# caller supplied API key credentials; otherwise fall back to altool with
# Apple ID + app-specific password.
UPLOAD_TOOL=""
if [[ -n "$API_KEY_ID" && -n "$API_ISSUER_ID" ]] && xcrun notarytool --help >/dev/null 2>&1; then
  UPLOAD_TOOL="notarytool"
elif xcrun altool --help >/dev/null 2>&1; then
  UPLOAD_TOOL="altool"
  if [[ -z "$APPLE_ID" || -z "$APP_SPECIFIC_PASSWORD" ]]; then
    echo "altool upload needs APPLE_ID + APP_SPECIFIC_PASSWORD (or --apple-id + --api-key-id/--api-issuer-id for notarytool)." >&2
    echo "  APPLE_ID:               ${APPLE_ID:+set}${APPLE_ID:-<missing>}" >&2
    echo "  APP_SPECIFIC_PASSWORD:  ${APP_SPECIFIC_PASSWORD:+<set>}${APP_SPECIFIC_PASSWORD:-<missing>}" >&2
    echo "  Get an app-specific password at https://appleid.apple.com → Sign-In and Security → App-Specific Passwords" >&2
    exit 2
  fi
elif xcrun notarytool --help >/dev/null 2>&1; then
  UPLOAD_TOOL="notarytool"
  if [[ -z "$API_KEY_ID" || -z "$API_ISSUER_ID" ]]; then
    echo "notarytool upload needs --api-key-id + --api-issuer-id (App Store Connect → Users and Access → Keys)." >&2
    exit 2
  fi
else
  echo "neither 'xcrun altool' nor 'xcrun notarytool' is available. Install/update Xcode command line tools." >&2
  exit 2
fi
echo "    upload tool: xcrun $UPLOAD_TOOL"

# Generate the .xcodeproj if needed (same as make-ipa.sh).
if [[ ! -d ios-app/RalphVC.xcodeproj ]]; then
  command -v xcodegen >/dev/null || { echo "install xcodegen: brew install xcodegen" >&2; exit 2; }
  ( cd ios-app && DEVELOPMENT_TEAM="$TEAM_ID" xcodegen generate )
fi

mkdir -p "$OUT"
ARCHIVE="$OUT/RalphVC.xcarchive"

# ----- 2. archive with App Store distribution signing ------------------------

echo "[2/5] archiving for App Store distribution"
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

# ----- 3. export a TestFlight-ready .ipa (method: app-store) -----------------

echo "[3/5] exporting App Store .ipa"
EXPORT_PLIST="$OUT/ExportOptions-appstore.plist"
sed "s/REPLACE_WITH_TEAM_ID/${TEAM_ID}/" \
  distribution/ExportOptions-appstore.plist > "$EXPORT_PLIST"

xcodebuild \
  -exportArchive \
  -archivePath "$ARCHIVE" \
  -exportPath  "$OUT/export" \
  -exportOptionsPlist "$EXPORT_PLIST"

cp "$OUT/export/RalphVC.ipa" "$OUT/RalphVC.ipa"

# ----- 4. upload to App Store Connect ----------------------------------------

echo "[4/5] uploading to App Store Connect via xcrun $UPLOAD_TOOL"
case "$UPLOAD_TOOL" in
  notarytool)
    # notarytool's --submit path is normally used for notarization, but
    # App Store Connect uploads go through `xcrun altool --upload-app` or
    # the newer `xcrun notarytool` transporter integration depending on
    # Xcode version. We shell out to whichever the local Xcode ships.
    xcrun altool --upload-app \
      --type ios \
      --file "$OUT/RalphVC.ipa" \
      --apiKey "$API_KEY_ID" \
      --apiIssuer "$API_ISSUER_ID"
    ;;
  altool)
    xcrun altool --upload-app \
      --type ios \
      --file "$OUT/RalphVC.ipa" \
      --username "$APPLE_ID" \
      --password "$APP_SPECIFIC_PASSWORD"
    ;;
esac

# ----- 5. done ----------------------------------------------------------------

echo "[5/5] done"
echo
echo "==============================================================="
echo "  RalphVC $VERSION (build $BUILD_NO) uploaded to App Store Connect."
echo "==============================================================="
echo
echo "  archive:  $ARCHIVE"
echo "  ipa:      $OUT/RalphVC.ipa"
echo
echo "Apple will process the build (usually a few minutes) and run a"
echo "light beta review — typically same-day, sometimes within hours."
echo
echo "Next, on https://appstoreconnect.apple.com:"
echo "  1. Open your app → TestFlight tab."
echo "  2. Wait for the build to show 'Ready to Test' (processing"
echo "     finishes automatically; beta review happens after that)."
echo "  3. Either:"
echo "       a) Add individual testers by email under Internal/External"
echo "          Testing → + , or"
echo "       b) Turn on Public Link under a testing group to get a"
echo "          shareable TestFlight URL (up to 10,000 testers, no UDID"
echo "          registration needed)."
echo
echo "Testers install by tapping the emailed 'View in TestFlight' link"
echo "or the public link, then installing from the TestFlight app —"
echo "the cleanest tap-to-download experience Apple offers."
