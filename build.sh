#!/bin/bash
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
case "$HERE" in /mnt/[a-z]/*) echo 'Copy this project into the WSL Linux filesystem first, or use Build.ps1.' >&2; exit 1;; esac
[ "$(id -u)" = 0 ] || { echo 'Run sudo ./build.sh' >&2; exit 1; }
# A fresh import location prevents stale source-directory .pyc reuse as well.
BUILD_IMPORTS=$(mktemp -d "${TMPDIR:-/tmp}/chatbox-imports-XXXXXX")
trap 'rmdir "$BUILD_IMPORTS"' EXIT
export CCACHE_DISABLE=1
python3 -B -X "pycache_prefix=$BUILD_IMPORTS" "$HERE/scripts/image.py" "$@"
