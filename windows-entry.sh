#!/bin/bash
set -euo pipefail
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[ ! -e "$SOURCE/out/chatbox-2.0.1-gpu-experimental-orangepi5-nvme.img.gz" ] || { echo 'Output already exists; move it before a new build.' >&2; exit 1; }
mkdir -p "$HOME/chatbox-builds"
DEST=$(mktemp -d "$HOME/chatbox-builds/2.0.1-gpu-experimental-XXXXXX")
printf 'Fresh WSL workspace: %s\n' "$DEST"
cp -R "$SOURCE/." "$DEST/"
cd "$DEST"
sudo bash setup-wsl.sh
sudo bash build.sh 2>&1 | tee build.log
mkdir -p "$SOURCE/out"
cp out/chatbox-2.0.1-gpu-experimental-orangepi5-nvme.img.gz* build.log "$SOURCE/out/"
printf 'Windows output folder: %s/out\n' "$SOURCE"
