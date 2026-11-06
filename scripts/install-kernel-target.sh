#!/bin/bash
# Runs only inside the offline ARM64 root under host QEMU/binfmt.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive LC_ALL=C
[ "$(dpkg --print-architecture)" = arm64 ] || { echo 'ARM64 root required'; exit 1; }
# No bootloader hooks may target an actual device from this build environment.
if dpkg-query -W -f='${Status}' flash-kernel 2>/dev/null | grep -qx 'install ok installed'; then
    echo 'Unexpected flash-kernel package; refusing offline bootloader actions'
    exit 1
fi
grep -qx 'U_BOOT_UPDATE=false' /etc/default/u-boot || exit 1
cd /run/chatbox-build
abi=$(cat KERNEL_ABI)
[[ "$abi" =~ ^[0-9A-Za-z.+_-]+$ ]] || exit 1
packages=()
while IFS='|' read -r package version file digest; do
    [[ "$file" =~ ^[0-9A-Za-z.+_~:-]+\.deb$ ]] || exit 1
    [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || exit 1
    [ "$(sha256sum "packages/$file" | cut -d' ' -f1)" = "$digest" ] || exit 1
    [ "$(dpkg-deb -f "packages/$file" Package)" = "$package" ] || exit 1
    [ "$(dpkg-deb -f "packages/$file" Version)" = "$version" ] || exit 1
    packages+=("packages/$file")
done <PACKAGES
# Python has pre-dependencies; configure the minimal chain before the full set.
for bootstrap in libpython3.13-minimal python3.13-minimal python3-minimal; do
    while IFS='|' read -r package version file digest; do
        if [ "$package" = "$bootstrap" ]; then dpkg --install "packages/$file"; fi
    done <PACKAGES
done
dpkg --install "${packages[@]}"
while IFS='|' read -r package version file digest; do
    [ "$(dpkg-query -W -f='${Status}|${Version}' "$package")" = "install ok installed|$version" ] || exit 1
done <PACKAGES
# Keep verification enabled and select the signer trusted by this vendor kernel.
/bin/sh /run/chatbox-build/select-regdb.sh
[ -s /usr/lib/firmware/regulatory.db ] || { echo 'Regulatory database missing'; exit 1; }
[ -s /usr/lib/firmware/regulatory.db.p7s ] || { echo 'Regulatory signature missing'; exit 1; }
# Include Panthor and its firmware in the completed image, before first boot.
grep -qx 'panthor' /etc/initramfs-tools/modules || echo panthor >> /etc/initramfs-tools/modules
# Rebuild after every package, including Debian's firmware alternatives, is configured.
update-initramfs -u -k "$abi"
[ -s "/boot/vmlinuz-$abi" ] || { echo 'Kernel image missing'; exit 1; }
[ -s "/boot/config-$abi" ] || { echo 'Kernel config missing'; exit 1; }
[ -s "/boot/initrd.img-$abi" ] || { echo 'ARM64 initramfs missing'; exit 1; }
lsinitramfs "/boot/initrd.img-$abi" > /run/chatbox-build/initrd-files
# Read the whole listing rather than causing an early pipe close.
grep -E 'arm/mali/arch10\.8/mali_csffw\.bin$' /run/chatbox-build/initrd-files >/dev/null
rm /run/chatbox-build/initrd-files
[ -s "/usr/lib/modules/$abi/modules.dep" ] || { echo 'Module dependency index missing'; exit 1; }
[ -s "/usr/lib/linux-image-$abi/rockchip/rk3588s-orangepi-5.dtb" ] || exit 1
[ -s /usr/lib/aarch64-linux-gnu/librkllmrt.so ] || exit 1
# Resolve all native runtime dependencies inside the target root.
/lib/ld-linux-aarch64.so.1 --list /usr/lib/aarch64-linux-gnu/librkllmrt.so
# Hardware cannot be enumerated under QEMU. Check native linkage only here.
[ -s /usr/lib/firmware/arm/mali/arch10.8/mali_csffw.bin ] || exit 1
[ -s /etc/OpenCL/vendors/rusticl.icd ] || exit 1
[ -s /usr/share/vulkan/icd.d/panfrost_icd.json ] || exit 1
[ -s /usr/lib/aarch64-linux-gnu/libvulkan_panfrost.so ] || exit 1
[ ! -e /usr/lib/aarch64-linux-gnu/libmali.so.1 ] || { echo 'Unexpected proprietary Mali library'; exit 1; }
/lib/ld-linux-aarch64.so.1 --list /usr/lib/aarch64-linux-gnu/libvulkan_panfrost.so
rusticl=$(cat /etc/OpenCL/vendors/rusticl.icd)
# The Debian manifest contains a library basename; loader resolution is checked below.
case "$rusticl" in libRusticlOpenCL.so*) ;; *) echo 'Unexpected Rusticl ICD'; exit 1;; esac
ldconfig -p | grep -F "$rusticl" >/dev/null
/lib/ld-linux-aarch64.so.1 --list /usr/local/sbin/chatbox-opencl-check
/lib/ld-linux-aarch64.so.1 --list /usr/local/sbin/chatbox-vulkan-check
/usr/bin/python3 -c "import http.server, http.client, json, threading, socket"
command -v clinfo
command -v aplay
command -v arecord
printf 'Offline ARM64 hardware preparation completed: %s\n' "$abi"
