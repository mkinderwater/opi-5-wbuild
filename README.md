# Chatbox image 2.0.1 GPU experiment

**Source-only Windows/WSL builder for the original Orange Pi 5 8 GB, NVMe boot/root, Ethernet.** Experimental replacement GPU stack: Panthor + Mesa PanVK (Vulkan) + Rusticl (OpenCL). The working 1.9.0 installation is the fallback. Build and flash a separate test NVMe; do not overwrite that fallback.

## Build on Windows

Extract the entire folder. Open PowerShell in it:

```powershell
.\Build.ps1
```

Uses Debian WSL, installs build dependencies, creates a fresh Linux workspace, downloads hash-pinned inputs, compiles ARM64 kernel/modules/DTB and the two numeric GPU checkers, and prepares the ARM64 root/initramfs under QEMU before publishing an image. All driver/firmware/Mesa assets are included before boot. No on-device compiler preparation or setup reboot is required. No cache of downloaded inputs or compiled kernels is reused. Do not rerun an old workspace; use the Windows entry point for a new one.

Output:

```text
out/chatbox-2.0.1-gpu-experimental-orangepi5-nvme.img.gz
```

Edit only the provisioning values actually used in CONFIG.TXT, flash the generated image using your normal NVMe enclosure workflow, then install the test NVMe. Existing SPI NVMe boot support remains required; this builder does not write SPI or a live disk. First boot retains Ethernet DHCP, identities, credentials, SSH and NVMe expansion. A nonempty root password is required; no minimum password length is imposed.

## What changes

| Layer | Candidate |
| --- | --- |
| Kernel | Same Armbian source commit as 1.9.0; ABI 6.1.172-chatbox8-arm64 |
| GPU kernel driver | Existing Armbian Panthor backport, module |
| Vulkan | Debian Trixie-backports Mesa PanVK 26.1.6-1~bpo13+1 |
| OpenCL | Debian Trixie-backports Mesa Rusticl 26.1.6-1~bpo13+1, enabled for panfrost |
| GPU firmware | Hash-pinned firmware-misc-nonfree 20250410-2, arch10.8 CSF firmware |
| NPU | Retained vendor RKNPU 0.9.8 and RKLLM runtime 1.2.3 |
| Audio | Baseline ES8323/ES8388 support, plus explicit MAX98357A module |
| Container features | Explicitly carried overlay2, namespaces, cgroups, bridge/NAT, seccomp |

One driver owns the GPU. Proprietary Valhall is not built or activated in this experiment, and libmali is not installed. This is the necessary GPU ABI switch, not general removal of optional board features. Both APIs share Panthor through Mesa. This is a packaged backports candidate, not a claim that Mesa 25 has every feature listed in current Mesa development documentation.

## First boot checks

Connect Ethernet and SSH as root, then:

```bash
uname -r
chatbox-status --vet --compute --json > /root/gpu-image-status.json
RUSTICL_ENABLE=panfrost clinfo > /root/clinfo.txt 2>&1
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/panfrost_icd.json vulkaninfo --summary > /root/vulkan.txt 2>&1
systemctl --failed --no-pager
arecord -l
findmnt /
```

The checker executes and validates a numeric OpenCL kernel and a numeric Vulkan compute shader on a hardware Mali-G610. It never counts CPU software rendering as a GPU pass. OpenCL test also reports whether cl_khr_fp16 is advertised. Basic numeric success does not prove MLC or Whisper compatibility.

Share those reports before installing AI applications. Do not run old proprietary-libmali mount commands on this image; the existing MLC container launcher requires a new Mesa-compatible userspace environment. Existing native Whisper CPU tools can be installed separately. A successful NPU model inference is required before promoting this image.

All previous tests used no added cooling. This image imposes no cooldown wait or clock-policy tuning. Keep logging temperatures and clocks for comparisons.

## Validation limits

Host tests exercise provisioning, image layout, mount cleanup, dependencies, checker behavior, DT links and numeric-check failure handling. The real pinned DTB is compiled and validated separately. GPU shader SPIR-V and C API syntax are checked. The complete kernel/image and hardware/API execution have not been performed here. This is an unvalidated hardware candidate, not a proven upgrade.

See docs/BASELINE-AUDIT.md, docs/BUILD-AND-PINS.md and docs/ACCEPTANCE.md. Previous baseline documents are preserved under docs/baseline-1.9.0-reference/ as history only. They describe the old proprietary GPU stack and are not this release's instructions. Old application installers are deliberately not bundled; use stock application deployments after the platform passes.
