#!/usr/bin/env bash
# host.sh — publish the .ipa + manifest.plist + install.html somewhere
# Apple's `itms-services://` URL scheme will accept (i.e. HTTPS).
#
# Three providers are supported out of the box. All three give you a
# free HTTPS URL with no card required:
#   - cloudflare   → wrangler pages publish    (recommended; instant; permanent URL)
#   - netlify      → netlify deploy --prod      (instant; permanent URL)
#   - gh-pages     → push to gh-pages branch    (slowest first publish; permanent URL)
#
# Authored by Chase Eddies <source@distillative.ai>.

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./distribution/host.sh --provider <cloudflare|netlify|gh-pages> [build-dir]

Options:
  --provider P        Hosting provider (required)
  --site NAME         Project / site name (default: ralphvc)
  build-dir           Build dir from make-ipa.sh (default: build)

Examples:
  ./distribution/host.sh --provider cloudflare
  ./distribution/host.sh --provider netlify --site ralphvc-mike
  ./distribution/host.sh --provider gh-pages
USAGE
}

PROVIDER=""
SITE="ralphvc"
DIR="build"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider) PROVIDER="$2"; shift 2 ;;
    --site)     SITE="$2";     shift 2 ;;
    -h|--help)  usage; exit 0 ;;
    *)          DIR="$1";      shift ;;
  esac
done

[[ -z "$PROVIDER" ]] && { echo "missing --provider" >&2; usage; exit 2; }
[[ -f "$DIR/RalphVC.ipa" ]] || { echo "no RalphVC.ipa in $DIR/. run distribution/make-ipa.sh first." >&2; exit 2; }

# Make a self-contained directory we can publish.
PUB="$DIR/_publish"
rm -rf "$PUB"; mkdir -p "$PUB/icons"
cp "$DIR/RalphVC.ipa"   "$PUB/RalphVC.ipa"
cp "$DIR/manifest.plist" "$PUB/manifest.plist"
cp "$DIR/install.html"   "$PUB/index.html"
[[ -f web/icons/icon-180.png ]] && cp web/icons/icon-180.png "$PUB/icons/icon-180.png" || true
[[ -f web/icons/icon-512.png ]] && cp web/icons/icon-512.png "$PUB/icons/icon-512.png" || true

publish_url=""

case "$PROVIDER" in
  cloudflare)
    command -v wrangler >/dev/null || { echo "install wrangler: npm i -g wrangler" >&2; exit 2; }
    publish_url="$(wrangler pages deploy "$PUB" --project-name "$SITE" 2>&1 | tee /dev/tty \
      | awk '/https:\/\/.*pages.dev/ {print $NF; exit}')"
    ;;
  netlify)
    command -v netlify >/dev/null || { echo "install netlify-cli: npm i -g netlify-cli" >&2; exit 2; }
    publish_url="$(netlify deploy --dir="$PUB" --prod --json 2>/dev/null \
      | python3 -c 'import json,sys;print(json.load(sys.stdin)["deploy_url"])')"
    ;;
  gh-pages)
    command -v gh >/dev/null || { echo "install gh: brew install gh" >&2; exit 2; }
    REMOTE_URL="$(git config --get remote.origin.url)"
    SLUG="$(echo "$REMOTE_URL" | sed -E 's#.*github\.com[:/](.+)\.git#\1#')"
    OWNER="${SLUG%%/*}"; REPO="${SLUG##*/}"
    git worktree add /tmp/ralphvc-pages gh-pages 2>/dev/null \
      || git worktree add -b gh-pages /tmp/ralphvc-pages
    rm -rf /tmp/ralphvc-pages/*; cp -R "$PUB"/* /tmp/ralphvc-pages/
    ( cd /tmp/ralphvc-pages && git add . && git commit -m "deploy ralphvc" && git push -u origin gh-pages )
    publish_url="https://${OWNER}.github.io/${REPO}/"
    ;;
  *)
    echo "unknown provider: $PROVIDER" >&2; exit 2 ;;
esac

[[ -z "$publish_url" ]] && { echo "could not parse publish URL — check provider output" >&2; exit 1; }

echo
echo "====================================================="
echo "  Ralph VC OTA install URL (open this on your iPhone):"
echo
echo "    $publish_url"
echo
echo "  …or scan the QR code in the install page."
echo "====================================================="

# Re-render the install page with the real URLs so the itms-services://
# link points at the live manifest, then re-deploy.
python3 distribution/render_install_page.py \
  --bundle-id "${BUNDLE_ID:-com.distillative.ralphvc}" \
  --version   "${VERSION:-0.1.0}" \
  --output    "$PUB" \
  --ipa-url       "${publish_url%/}/RalphVC.ipa" \
  --manifest-url  "${publish_url%/}/manifest.plist"
mv "$PUB/install.html" "$PUB/index.html"

echo "redeploying with rewritten URLs…"
case "$PROVIDER" in
  cloudflare) wrangler pages deploy "$PUB" --project-name "$SITE" >/dev/null ;;
  netlify)    netlify deploy --dir="$PUB" --prod >/dev/null ;;
  gh-pages)   ( cd /tmp/ralphvc-pages && cp "$PUB/index.html" . && cp "$PUB/manifest.plist" . \
                && git add . && git commit -m "rewrite urls" --allow-empty && git push ) ;;
esac

echo "done. your iPhone-tappable install URL is:  $publish_url"
