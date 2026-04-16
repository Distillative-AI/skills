#!/usr/bin/env bash
# setup.sh — one-command "run Ralph VC on my iPhone" flow.
#
# What this script does:
#   1. Checks prerequisites (Xcode, xcodegen, the sibling ios-development skill).
#   2. Generates the .xcodeproj from ios-app/project.yml.
#   3. Starts the local server in the background (the iPhone POSTs to it).
#   4. Builds + installs + launches Ralph VC on a connected iPhone (or simulator).
#
# Authored by Chase Eddies <source@distillative.ai>.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# ----- color helpers ---------------------------------------------------------

c_blue()  { printf "\033[34m%s\033[0m\n" "$*"; }
c_green() { printf "\033[32m%s\033[0m\n" "$*"; }
c_red()   { printf "\033[31m%s\033[0m\n" "$*" >&2; }

# ----- 0. usage --------------------------------------------------------------

usage() {
  cat <<'USAGE'
Usage: ./setup.sh [--simulator | --device --team-id ABCDE12345] [--no-server]

Examples:
  # First-time run on a tethered iPhone:
  export ANTHROPIC_API_KEY=sk-ant-...
  ./setup.sh --device --team-id ABCDE12345

  # Iterate on the simulator (no team id needed):
  ./setup.sh --simulator

  # Skip starting the server (e.g. you already have it running):
  ./setup.sh --simulator --no-server
USAGE
}

TARGET=""
TEAM_ID=""
START_SERVER=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --simulator) TARGET=simulator; shift ;;
    --device)    TARGET=device;    shift ;;
    --team-id)   TEAM_ID="$2";     shift 2 ;;
    --no-server) START_SERVER=0;   shift ;;
    -h|--help)   usage; exit 0 ;;
    *)           c_red "unknown arg: $1"; usage; exit 2 ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  c_red "missing --simulator or --device"
  usage; exit 2
fi
if [[ "$TARGET" == "device" && -z "$TEAM_ID" ]]; then
  c_red "device builds need --team-id <APPLE_DEVELOPER_TEAM_ID>"
  c_red "find yours at https://developer.apple.com/account → Membership"
  exit 2
fi

# ----- 1. prereqs ------------------------------------------------------------

c_blue "[1/4] checking prerequisites"

if [[ "$(uname -s)" != "Darwin" ]]; then
  c_red "this script must run on macOS — Xcode is required to build iOS apps."
  exit 2
fi

command -v xcrun     >/dev/null || { c_red "xcrun not found. Install Xcode."; exit 2; }
command -v xcodebuild >/dev/null || { c_red "xcodebuild not found. Install Xcode."; exit 2; }
command -v xcodegen  >/dev/null || {
  c_blue "    xcodegen not found, installing via Homebrew (one-time)..."
  command -v brew >/dev/null || { c_red "Homebrew is required. https://brew.sh"; exit 2; }
  brew install xcodegen
}

# Resolve the sibling ios-development skill (deploy.py + orchestrator live there).
IOS_DEV_SKILL=""
for candidate in "$HERE/../ios-development" "$HERE/../../skills/ios-development"; do
  if [[ -f "$candidate/app/deploy.py" ]]; then
    IOS_DEV_SKILL="$(cd "$candidate" && pwd)"
    break
  fi
done
if [[ -z "$IOS_DEV_SKILL" ]]; then
  c_red "could not find the sibling 'ios-development' skill (need its app/deploy.py)."
  c_red "install both skills from the marketplace, or clone them next to each other."
  exit 2
fi
c_green "    ios-development skill: $IOS_DEV_SKILL"

# Anthropic API key (required for the orchestrator to talk to Sonnet).
if [[ "$START_SERVER" == "1" && -z "${ANTHROPIC_API_KEY:-}" ]]; then
  c_red "ANTHROPIC_API_KEY is unset. Get one at https://console.anthropic.com"
  c_red "and: export ANTHROPIC_API_KEY=sk-ant-..."
  exit 2
fi

# Bearer token between the iPhone and the local server.
if [[ -z "${RALPHVC_BEARER:-}" ]]; then
  c_blue "    RALPHVC_BEARER not set, generating an ephemeral one for this run"
  export RALPHVC_BEARER="$(uuidgen | tr -d '-' | head -c 32)"
  c_green "    RALPHVC_BEARER=$RALPHVC_BEARER"
  c_green "    (paste this into the iPhone app's Settings, then save it to the keychain)"
fi

# ----- 2. generate the .xcodeproj -------------------------------------------

c_blue "[2/4] generating ios-app/RalphVC.xcodeproj"
( cd ios-app && DEVELOPMENT_TEAM="$TEAM_ID" xcodegen generate )

# ----- 3. start the server in the background --------------------------------

SERVER_PID=""
if [[ "$START_SERVER" == "1" ]]; then
  c_blue "[3/4] starting localhost orchestrator server on :7878"
  python3 server/server.py --host 0.0.0.0 --port 7878 \
    > /tmp/ralphvc-server.log 2>&1 &
  SERVER_PID=$!
  sleep 0.5
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    c_red "server failed to start. Tail of log:"
    tail -20 /tmp/ralphvc-server.log >&2
    exit 1
  fi
  c_green "    server pid=$SERVER_PID  log=/tmp/ralphvc-server.log"
  trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
else
  c_blue "[3/4] --no-server: skipping local orchestrator startup"
fi

# ----- 4. build + install + launch ------------------------------------------

c_blue "[4/4] deploying RalphVC to $TARGET"

DEPLOY_ARGS=(
  --project ios-app/RalphVC.xcodeproj
  --scheme  RalphVC
  --target  "$TARGET"
)
if [[ "$TARGET" == "device" ]]; then
  DEPLOY_ARGS+=(--team-id "$TEAM_ID")
fi

python3 "$IOS_DEV_SKILL/app/deploy.py" "${DEPLOY_ARGS[@]}"

c_green "
done.

Next steps:
  - The Ralph VC app is now running on your $TARGET.
  - The local server is listening on http://0.0.0.0:7878 (PID $SERVER_PID).
  - On the iPhone, point Settings → Endpoint at http://<your-mac-ip>:7878
    and paste your bearer token: $RALPHVC_BEARER
  - Tap the mic and start vibe-coding.

To stop the server: kill $SERVER_PID
To watch logs:      tail -f /tmp/ralphvc-server.log
"

# Keep the server alive until the user Ctrl-Cs (or close the script if --no-server).
if [[ "$START_SERVER" == "1" ]]; then
  c_blue "(server is still running — Ctrl-C to stop)"
  wait "$SERVER_PID"
fi
