# Debian initramfs helper regression fixture

`debian-copy-file.sh` contains the unmodified copy_file function from
initramfs-tools-core 0.148.4, plus attribution comments. The tests source the
real function and relocate only the hook source/helper paths into fixtures.
This reproduces return 1 for an already present destination, unlike the old stub.

Package: https://deb.debian.org/debian/pool/main/i/initramfs-tools/initramfs-tools-core_0.148.4_all.deb
SHA-256: 03cb11b8acd188e3b441526698536694f515ea6f2f5a20aef5ae70e5eb485a7a
Upstream: https://salsa.debian.org/kernel-team/initramfs-tools

License: GPL-2.0-or-later. Copyright attribution and terms are retained in
initramfs-tools-copyright; the GPL version 2 text is included as GPL-2.

Tests cover missing first-pass inputs, new copies, both existing copies,
one existing copy, mismatched existing data and genuine I/O failure.
The fixture is test-only; production uses Debian's installed hook-functions.
