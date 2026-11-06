# Pinned upstream components

- Debian Trixie ARM64 root: Johang sd-card-images. URL/SHA-256 in scripts/image.py.
  Debian package licences remain under /usr/share/doc in the resulting image.
  https://github.com/johang/sd-card-images
- Kernel: Armbian's maintained Rockchip vendor tree, commit
  85233a85b67928000afc2e966bab86a8c414f1b4. Archive hash in hardware-lock.json.
  GPL-2.0 and component-specific terms in that source. The Valhall driver and
  its embedded firmware come from this same pinned source, not a separate
  unverified firmware download. Kernel package includes source provenance,
  fragment and upstream COPYING/GPL text. Retain corresponding source when
  redistributing locally built binary images.
  https://github.com/armbian/linux-rockchip/commit/85233a85b67928000afc2e966bab86a8c414f1b4
- RKLLM 1.2.3: Rockchip commit f7df8e5de9b40dc7aaa66194cf14d4895aaf159a.
  Runtime and licence hashes pinned. Copyright installed with the runtime.
  https://github.com/airockchip/rknn-llm/tree/f7df8e5de9b40dc7aaa66194cf14d4895aaf159a
- Mali OpenCL userspace: ginkage/libmali-rockchip commit
  334a20c1a34f43d1c00b2b29e4df5cf9cb3d5fe7. ARM Mali proprietary binary and
  copyright notice are downloaded and verified at build time. The upstream
  copyright/licence text is installed under /usr/share/doc/chatbox-mali-opencl.
  https://github.com/ginkage/libmali-rockchip/tree/334a20c1a34f43d1c00b2b29e4df5cf9cb3d5fe7
- ALSA, libgomp, OpenCL loader/headers/dev files and clinfo: pinned Debian Trixie
  package identities and SHA-256 values in inputs/hardware-lock.json.
- Coordinator runtime: pinned Debian Python 3.13 and standard-library packages.
  No Python packages are downloaded with pip. Copyright files are installed by dpkg.
- QEMU/binfmt and cross compiler are host build dependencies, not target binaries.
- Account/FAT/DTB helpers originate from the supplied BPI builder; BPI board
  firmware, driver binaries and wireless setup are not included.

The source ZIP contains no downloaded kernel/runtime binaries or OS images.
The existing SPI bootloader is neither distributed nor modified by this release.
# 1.9.0 regulatory firmware addition

Debian wireless-regdb 2026.05.30-1~deb13u1 supplies regulatory.db and its
signature for retained cfg80211 support. The exact package hash is pinned in
hardware-lock.json. Its copyright/license is installed under
/usr/share/doc/wireless-regdb/copyright. No wireless driver is disabled.

