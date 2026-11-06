#!/bin/bash
# Existing-board repair. No downloads, SPI writes or kernel recompilation.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[ "$(id -u)" = 0 ] || { echo 'Run as root on the board.' >&2; exit 1; }
abi=$(uname -r)
[ "$abi" = '6.1.172-chatbox8-arm64' ] || {
    echo 'This repair is verified for the Chatbox chatbox8 kernel only.' >&2; exit 1;
}
package_version=$(dpkg-query -W -f='${Version}' wireless-regdb)
[ "$package_version" = '2026.05.30-1~deb13u1' ] || {
    echo 'This repair requires the pinned wireless-regdb 2026.05.30-1~deb13u1 package.' >&2; exit 1;
}
# Preserve signature verification. This does not change country or radio policy.
sh "$HERE/inputs/select-upstream-regdb.sh"
install -m 0755 "$HERE/inputs/initramfs-regdb-hook" /etc/initramfs-tools/hooks/chatbox-regdb
update-initramfs -u -k "$abi"
# The diagnostic installer writes only the four bundled diagnostic files.
bash "$HERE/scripts/install-checker.sh"
echo 'Upstream regulatory database selected; initramfs rebuilt; checker updated.'
echo 'Reboot, then run: chatbox-status --vet --compute --json > /tmp/chatbox-status-fixed.json'
