#!/usr/bin/env bash
# build.sh — thin, opinionated wrapper around xcodebuild for use from
# Claude Code Cloud. Runs build / test / clean against a simulator
# destination by default.
#
# Authored by Chase Eddies <source@distillative.ai>.

set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: build.sh <command> [options]

Commands:
  build     xcodebuild build (default)
  test      xcodebuild test
  clean     xcodebuild clean

Options:
  --project PATH         .xcodeproj path
  --workspace PATH       .xcworkspace path (overrides --project)
  --scheme NAME          required
  --configuration NAME   defaults to Debug
  --destination STRING   forwarded as -destination (default: iPhone simulator)
  --derived-data PATH    -derivedDataPath
  -h, --help             show this help

Any args after `--` are forwarded verbatim to xcodebuild.
USAGE
}

CMD="build"
case "${1:-}" in
    build|test|clean) CMD="$1"; shift ;;
    -h|--help) usage; exit 0 ;;
esac

PROJECT=""
WORKSPACE=""
SCHEME=""
CONFIG="Debug"
DEST=""
DERIVED=""
EXTRA=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project)        PROJECT="$2"; shift 2 ;;
        --workspace)      WORKSPACE="$2"; shift 2 ;;
        --scheme)         SCHEME="$2"; shift 2 ;;
        --configuration)  CONFIG="$2"; shift 2 ;;
        --destination)    DEST="$2"; shift 2 ;;
        --derived-data)   DERIVED="$2"; shift 2 ;;
        -h|--help)        usage; exit 0 ;;
        --)               shift; EXTRA=("$@"); break ;;
        *)                echo "unknown arg: $1" >&2; usage; exit 2 ;;
    esac
done

if [[ -z "$SCHEME" ]]; then
    echo "build.sh: --scheme is required" >&2
    exit 2
fi

ARGS=()
if [[ -n "$WORKSPACE" ]]; then
    ARGS+=(-workspace "$WORKSPACE")
elif [[ -n "$PROJECT" ]]; then
    ARGS+=(-project "$PROJECT")
fi
ARGS+=(-scheme "$SCHEME" -configuration "$CONFIG")
[[ -n "$DERIVED" ]] && ARGS+=(-derivedDataPath "$DERIVED")

if [[ -z "$DEST" ]]; then
    DEST="platform=iOS Simulator,name=iPhone 15"
fi
ARGS+=(-destination "$DEST")

set -x
exec xcodebuild "${ARGS[@]}" "${EXTRA[@]}" "$CMD"
