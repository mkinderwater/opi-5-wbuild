# Chatbox Image 2.0.1 (GPU Experimental)

A reproducible, source-only image builder for the **Orange Pi 5 (RK3588S, 8 GB)** that produces a bootable Debian Trixie ARM64 NVMe image with an open-source GPU compute stack (Panthor + Mesa PanVK Vulkan + Mesa Rusticl OpenCL), the Rockchip NPU, onboard audio and container support, ready for an offline, on-device AI voice assistant.

The build runs entirely on Windows through Debian WSL2. Every downloaded input is pinned by hash, every build starts from a fresh workspace, and the finished image boots straight to Ethernet and SSH with no on-device compiling or setup reboots.

> **Status: experimental.** This release swaps the proprietary Mali (Valhall/libmali) GPU stack used in 1.9.0 for the open Panthor/Mesa stack. Host tests pass, but the full image has not yet been validated on hardware. Flash it to a **separate test NVMe** and keep a known-good drive as your rollback.

---

## Purpose

Chatbox is a platform for a small, private, offline desktop voice companion: short conversations, stories, games, simple questions, timers and explicitly saved memory, all processed locally with no cloud services.

This repository builds the **base operating system image** for that appliance. It is responsible for getting the hardware right (kernel, device tree, drivers, firmware, GPU and NPU userspace) and making the board reachable and diagnosable. AI applications (LLM, speech recognition, text to speech) are installed separately once the platform passes its acceptance checks.

The 2.0.1 experiment exists to answer one question: can the open Mesa GPU drivers on RK3588 deliver usable Vulkan and OpenCL compute for workloads like whisper.cpp and MLC-LLM, while keeping the NPU, audio and everything else from the proven 1.9.0 baseline intact?

## Features

### Build system
- **One-command Windows build.** `Build.ps1` drives Debian WSL2, installs host dependencies, cross-compiles and assembles the image.
- **Fresh, cache-free builds.** Each run copies the source into a new WSL workspace. No previously downloaded inputs, compiled kernels or `ccache` results are reused.
- **Hash-pinned inputs.** The Debian root image, kernel source archive, Mesa packages, firmware and their full dependency closure are pinned by URL and SHA-256 in `inputs/hardware-lock.json`. A missing or changed upstream file fails the build rather than silently substituting a different version.
- **Fully staged before first boot.** The ARM64 kernel, modules, DTB, initramfs and GPU checkers are built on the host, and the target root is prepared under QEMU user emulation. Driver, firmware and Mesa assets are verified inside the image before it is published.
- **Provenance recorded.** Source hashes, package hashes and build metadata are written into the image.

### Platform
| Layer | Component |
| --- | --- |
| Base OS | Debian Trixie ARM64 (johang/sd-card-images root, hash pinned) |
| Kernel | Armbian `linux-rockchip` vendor tree, commit `85233a8`, ABI `6.1.172-chatbox8-arm64` |
| Recovery kernel | Debian `6.12.113+deb13-arm64` with its own DTB, selectable at boot |
| GPU kernel driver | Panthor (Armbian backport, built as a module) |
| Vulkan | Mesa PanVK 26.1.6 (Debian Trixie-backports) |
| OpenCL | Mesa Rusticl 26.1.6, enabled for `panfrost` |
| GPU firmware | `firmware-misc-nonfree` 20250410-2, Mali CSF `arch10.8` |
| NPU | Rockchip RKNPU 0.9.8 driver with RKLLM runtime 1.2.3 |
| Audio | Onboard ES8323/ES8388 codec, plus MAX98357A I2S amplifier module |
| Containers | overlay2, namespaces, cgroups, bridge/veth, NAT/nftables, seccomp |
| Boot and storage | Existing SPI bootloader, NVMe boot and root, no SD card required |
| Network | Ethernet with DHCP |

A single driver owns the GPU. The proprietary Valhall driver and libmali are not built or installed, so both Vulkan and OpenCL share Panthor through Mesa.

### First boot provisioning
- Reads `ROOT_PASSWORD`, `TIMEZONE` and `HOSTNAME` from `CONFIG.TXT` on the image's small FAT config partition.
- Sets the root password, timezone and hostname, generates unique machine identity and SSH host keys, then **scrubs the password** from `CONFIG.TXT`.
- Expands the root partition to fill the NVMe, with strict device identity checks before any partition change.
- Waits for Ethernet DHCP and SSH readiness, retrying until the board is reachable.

### Built-in diagnostics
All tools live in `/usr/local/sbin` and are read-only unless noted.

| Command | What it does |
| --- | --- |
| `chatbox-status` | Inventory and health report. `--vet` checks release fixes, assets, hashes, expansion, failed units and time sync. `--compute` runs real GPU tests. `--containers` checks kernel container capabilities. `--json` for machine output. |
| `chatbox-opencl-check` | Runs a numeric OpenCL kernel on the Mali-G610 and validates the results. Reports `cl_khr_fp16` support. |
| `chatbox-vulkan-check` | Runs a numeric SPIR-V compute shader through the PanVK ICD only and validates the results. |
| `chatbox-hardware-check` | Verifies ALSA cards, ES8388 registration and the RKNPU 0.9.8 driver. |
| `chatbox-board-report` | JSON report of board, DRM, audio and device-tree state. |
| `chatbox-container-test` | Functional Docker test (pulls a pinned ARM64 image and creates temporary resources, so it is **not** read-only). |
| `chatbox-diag` | Combined text diagnostic dump that excludes passwords, private keys and recordings. |
| `chatbox-metrics` | Clocks, temperatures and memory. |
| `chatbox-select-kernel display\|recovery` | Chooses the main or Debian recovery kernel for the next boot, after verifying its files and initramfs drivers. |

The GPU checkers refuse to count CPU software rendering (llvmpipe/lavapipe) as a pass. A GPU test only passes on real Mali-G610 hardware with correct numeric output.

### Local model coordinator
- `chatbox-app.service` runs a small, stateless Python coordinator on `127.0.0.1:8088` exposing `/health`, `/ready`, `/diagnostics` and an OpenAI-style `/v1/chat/completions` endpoint (including streaming).
- It only forwards to **local** backends you configure in `/etc/chatbox/app.json`. It downloads nothing and accepts no remote endpoints.
- Hardened with systemd sandboxing: dynamic non-root user, no capabilities, strict filesystem protection, 128 MB memory cap.
- Shipped **unconfigured**. `chatbox-api health|ready|diagnostics|chat "message" [--stream]` talks to it from the shell.

## Hardware requirements

- Original **Orange Pi 5** (RK3588S), 8 GB RAM recommended
- NVMe SSD (use a separate test drive for this release)
- SPI flash already holding an NVMe-capable bootloader (this builder never writes SPI)
- Wired Ethernet with DHCP
- Adequate power supply

## Building

### Requirements
- Windows 10/11 with WSL2 and the **Debian** distribution installed
- Internet access for the pinned downloads
- Several GB of free space in the WSL filesystem

### Steps
1. Download or clone this repository and extract the full folder.
2. Open PowerShell in the folder and run:

   ```powershell
   .\Build.ps1
   ```

   Use `.\Build.ps1 -Distribution <name>` if your Debian WSL distribution has a different name.

3. The finished image is written to:

   ```text
   out/chatbox-2.0.1-gpu-experimental-orangepi5-nvme.img.gz
   ```

   along with `build.log`. Move an existing output out of `out/` before building again.

Building directly inside Linux or WSL is also possible: copy the project into the Linux filesystem (not `/mnt/c/...`), then run `sudo ./setup-wsl.sh` followed by `sudo ./build.sh`.

## Flashing and first boot

1. Flash the `.img.gz` to your test NVMe using your usual enclosure and imaging tool.
2. Edit `CONFIG.TXT` on the image's FAT config partition:

   ```ini
   ROOT_PASSWORD=your-password
   TIMEZONE=America/Edmonton
   HOSTNAME=chatbox
   ```

   `ROOT_PASSWORD` is required. `TIMEZONE` defaults to `America/Edmonton`. `HOSTNAME` is optional.
3. Install the NVMe in the Orange Pi 5, connect Ethernet and power on.
4. Find the board's DHCP address and connect with `ssh root@<address>`.

## Verifying the image

Run these after first boot and keep the output for comparison:

```bash
uname -r                                   # expect 6.1.172-chatbox8-arm64
chatbox-status --vet --compute --json > /root/gpu-image-status.json
RUSTICL_ENABLE=panfrost clinfo > /root/clinfo.txt 2>&1
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/panfrost_icd.json vulkaninfo --summary > /root/vulkan.txt 2>&1
systemctl --failed --no-pager
arecord -l
findmnt /
```

Promotion of this image beyond experimental follows the gates in [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md):

1. **Boot and registration:** kernel, Ethernet, SSH, NVMe expansion, HDMI, ES8388 audio, no failed units.
2. **Both GPU APIs:** independent numeric passes for OpenCL and Vulkan on hardware.
3. **NPU and audio preserved:** real RKLLM generation, container networking and limits, microphone capture.
4. **Application acceleration:** whisper.cpp CPU versus Vulkan on identical inputs; MLC on a Mesa-compatible userspace.
5. **Sustained operation:** repeated boots, long and concurrent ASR/LLM/TTS workloads, temperature and latency logging.

A simple numeric pass shows the GPU works. It does not prove that a given application (MLC-LLM, whisper.cpp) has every Vulkan or OpenCL feature it needs, such as fp16 or subgroup support.

## Rollback

Rollback is a drive swap: power off and reinstall your known-good NVMe. Do not mix the kernel, DTB, firmware or libmali files between 1.9.0 and 2.0.1 images. The Debian recovery kernel is also available on the image via `chatbox-select-kernel recovery`.

## Compatibility notes

- MLC-LLM containers built for 1.9.0 mount proprietary libmali and **will not work unchanged** on this image. They need a new Mesa-compatible userspace.
- Services and containers that need OpenCL must set `RUSTICL_ENABLE=panfrost` themselves. Login shells get it from `/etc/profile.d/chatbox-rusticl.sh`.
- Do not assume `renderD129` is the NPU. Adding a GPU DRM driver can change render node numbers, so match devices by driver identity under `/sys/class/drm/renderD*/device/driver`.
- No cooling, cooldown wait or clock policy changes are imposed.

## Repository layout

```text
Build.ps1               Windows entry point (runs the build in Debian WSL)
windows-entry.sh        Creates a fresh WSL workspace and copies results back
setup-wsl.sh            Installs host build dependencies and ARM64 binfmt
build.sh                Linux build entry point
CONFIG.TXT              First boot provisioning template
SHA256SUMS              Hashes of the source release files
scripts/                Image assembly, vendor/kernel staging, FAT32 and DTB helpers,
                        OpenCL and Vulkan checker sources
inputs/                 Kernel config fragment, board DT fixes, hash lock file,
                        regulatory database hooks
overlay/                Files installed into the target root (systemd units,
                        diagnostics, coordinator, udev rules)
tests/                  Host test suite
docs/                   Build pins, baseline audit, acceptance gates, verification limits
docs/baseline-1.9.0-reference/
                        Historical 1.9.0 documents (old proprietary GPU stack,
                        reference only)
```

## Testing

The host test suite covers provisioning, image layout, mount cleanup, dependency resolution, device tree links, checker behaviour and GPU check failure handling:

```bash
python3 -m unittest discover -s tests
```

Some tests skip when a tool they need (for example a software Vulkan ICD) is unavailable. See [`docs/LOCAL-VERIFICATION.md`](docs/LOCAL-VERIFICATION.md) for what has and has not been verified.

## Documentation

- [`docs/BUILD-AND-PINS.md`](docs/BUILD-AND-PINS.md): how inputs are selected and pinned
- [`docs/BASELINE-AUDIT.md`](docs/BASELINE-AUDIT.md): what changed from 1.9.0 and why
- [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md): hardware acceptance gates and rollback
- [`docs/LOCAL-VERIFICATION.md`](docs/LOCAL-VERIFICATION.md): verification performed and its limits

## Third-party components

This repository contains source and build scripts only. It does not include any OS image, compiled kernel, firmware binary, Debian package or model. All of these are downloaded and verified at build time from their upstream sources, including:

- Debian Trixie ARM64 root from [johang/sd-card-images](https://github.com/johang/sd-card-images)
- [Armbian linux-rockchip](https://github.com/armbian/linux-rockchip) kernel source (GPL-2.0)
- Mesa PanVK, Rusticl, Linux firmware and supporting packages from the Debian archive
- [Rockchip RKLLM](https://github.com/airockchip/rknn-llm) runtime

Each component remains under its own license. Debian package licences are installed under `/usr/share/doc` in the resulting image. If you redistribute a built image, you are responsible for providing corresponding kernel source as required by the GPL.

## License

<!-- Add your chosen license here, e.g. MIT or GPL-2.0, and include a LICENSE file. -->

## Author

Matthew Kinderwater, ICUBEDEV CGY ([icubedev.com](https://icubedev.com)), Calgary, Alberta.
