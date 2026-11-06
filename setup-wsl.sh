#!/bin/bash
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo 'Run sudo ./setup-wsl.sh'; exit 1; }
apt-get update
apt-get install -y --no-install-recommends python3 dpkg curl ca-certificates e2fsprogs initramfs-tools-core cpio gzip zstd xz-utils qemu-user-static binfmt-support kmod util-linux build-essential gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu libc6-dev-arm64-cross flex bison bc libssl-dev libelf-dev pkg-config glslang-tools
# Register only ARM64; leave Windows interoperability and other handlers alone.
mkdir -p /proc/sys/fs/binfmt_misc
if ! mountpoint -q /proc/sys/fs/binfmt_misc; then
    mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
fi
update-binfmts --enable qemu-aarch64
python3 - <<'PY'
from pathlib import Path
import re
p=Path('/proc/sys/fs/binfmt_misc/qemu-aarch64')
if not p.is_file():raise SystemExit('ARM64 binfmt registration failed')
s=p.read_text();m=re.search(r'^flags:\s*(\S+)',s,re.M)
if not s.startswith('enabled\n') or not m or 'F' not in m[1]:
    raise SystemExit('ARM64 binfmt requires fix-binary (F) support. Update qemu-user-static/binfmt packages.')
print('ARM64 build emulation enabled. Build with sudo ./build.sh')
PY
