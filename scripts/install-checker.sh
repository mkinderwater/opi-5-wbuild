#!/bin/bash
# Install diagnostics only. No kernel, boot, model, service or configuration writes.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
target_root=${DESTDIR:-}
if [ -z "$target_root" ] && [ "$(id -u)" != 0 ]; then
    echo 'Run as root on the board.' >&2; exit 1
fi
[ -f "$target_root/usr/local/lib/chatbox/coordinator.py" ] || {
    echo 'Existing Chatbox Python/coordinator installation required.' >&2; exit 1;
}
for file in acceptance.py board_report.py containers.py container-profile.json container-test-input.json; do
    [ -f "$HERE/overlay/usr/local/lib/chatbox/$file" ] || exit 1
done
for file in chatbox-status chatbox-hardware-check chatbox-container-test; do
    [ -f "$HERE/overlay/usr/local/sbin/$file" ] || exit 1
done
install -d "$target_root/usr/local/lib/chatbox" "$target_root/usr/local/sbin"
for file in acceptance.py board_report.py containers.py container-profile.json container-test-input.json; do
    install -m 0644 "$HERE/overlay/usr/local/lib/chatbox/$file" "$target_root/usr/local/lib/chatbox/$file"
done
for file in chatbox-hardware-check chatbox-status chatbox-container-test; do
    install -m 0755 "$HERE/overlay/usr/local/sbin/$file" "$target_root/usr/local/sbin/$file"
done
echo 'Checker 2.0.1-gpu-experimental installed. Image/kernel unchanged.'
echo 'Run: chatbox-status --vet --compute --json > /tmp/chatbox-status.json'
