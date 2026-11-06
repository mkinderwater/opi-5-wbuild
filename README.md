# Chatbox Image 2.0.1 (GPU Experimental)

A reproducible, source-only image builder for the **Orange Pi 5 (RK3588S, 8 GB)** that produces a bootable Debian Trixie ARM64 NVMe image with an open-source GPU compute stack (Panthor + Mesa PanVK Vulkan + Mesa Rusticl OpenCL), the Rockchip NPU, onboard audio and container support, ready for an offline, on-device AI voice assistant.

The build runs entirely on Windows through Debian WSL2. Every downloaded input is pinned by hash, every build starts from a fresh workspace, and the finished image boots straight to Ethernet and SSH with no on-device compiling or setup reboots.

> **Status: experimental, running on real hardware.** This release swaps the proprietary Mali (Valhall/libmali) GPU stack used in 1.9.0 for the open Panthor/Mesa stack. 2.0.1 (`6.1.172-chatbox8-arm64`) has booted on an Orange Pi 5 8 GB and was the platform underneath the accepted voice assistant tests. Numeric OpenCL and Vulkan checks and Docker functionality passed in a later on-board audit. Full acceptance (all five gates below, including sustained thermal testing) is **not** complete. See [Real-world test results](#real-world-test-results).

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

### Acceptance progress

| Gate | Status on real hardware |
| --- | --- |
| 1. Boot and registration | Booted and used as the running platform (`chatbox8` kernel, NVMe root expanded to about 235 GB, ES8388 audio working). Some NPU, regulator/OPP, OP-TEE and SCMI boot warnings remain. |
| 2. Both GPU APIs | Numeric OpenCL and Vulkan checks passed. Vulkan reports FP16; BF16 and matrix cores are not reported. OpenCL FP16 is not separately established. |
| 3. NPU and audio preserved | Real RKLLM generation on the NPU confirmed. Docker and Open WebUI ran. Microphone capture and headphone playback working. |
| 4. Application acceleration | Vulkan tested with Piper TTS only (slower than CPU, see below). whisper.cpp Vulkan and MLC on Rusticl not yet tested. |
| 5. Sustained operation | Not done. No temperature, power or long-run data yet. |

## Real-world test results

These results come from hands-on testing on an original Orange Pi 5 (RK3588S, 8 GB) running this 2.0.1 image, recorded in the November 6, 2026 community test report. They are measurements of particular runs, not performance guarantees. **Cooling, ambient temperature and power were not recorded for these captures.** Run IDs are the Pi's own benchmark directory names; their timezone was not recorded.

### Test platform

| Item | Value |
| --- | --- |
| Board / RAM | Original Orange Pi 5, 8 GB |
| SoC | Rockchip RK3588S: 4x Cortex-A76 (cores 4-7), 4x Cortex-A55 (cores 0-3) |
| GPU | Mali-G610 MC4, Panthor + Mesa 26.1.6 PanVK/Rusticl |
| NPU | RKNPU 0.9.8 driver, RKLLM 1.2.3 runtime, 3 NPU cores |
| Kernel | `6.1.172-chatbox8-arm64` (Chatbox 2.0.1) |
| Storage | NVMe, root `/dev/nvme0n1p2`, about 235 GB after expansion |
| Audio | Onboard ES8388 codec, headphone out and onboard mic |
| CPU governor | `schedutil` (image default) unless stated |
| Cooling | Not recorded for the timing captures |

### Software under test

| Work | Engine | Pin | Runs on |
| --- | --- | --- | --- |
| Chat | Qwen2.5 1.5B Instruct W8A8, RKLLM | model SHA-256 `060ea964...b64b2e` | NPU |
| Chat HTTP API | GatekeeperZA RKLLM-API-Server, project-adapted | `89f43f9` | CPU |
| Speech recognition | whisper.cpp v1.9.5, `tiny.en`, 4 threads | `d1be6fd` | CPU |
| Speech synthesis | audio.cpp v0.9.3, Piper en-US Lessac Medium GGUF, 4 threads | `41c1f8f` | CPU (Vulkan tested) |
| Browser UI | Open WebUI v0.12.5, Docker, 2 GiB memory limit | pinned digest | CPU |
| Document embeddings | all-MiniLM-L6-v2, batch 1 | `1110a24` | CPU |

### Measurement definitions

| Term | Meaning |
| --- | --- |
| First text | Client-observed arrival of the first generated text, not answer completion |
| WAV ready | Synthesis finished, including the overhead stated for that test |
| First player | Software playback process launched; not an acoustic measurement of first audible sample |
| RTF | Real-time factor: synthesis time divided by audio duration. Below 1.0 is faster than real time |
| NPU completion | Total time for the whole answer. Output lengths differ, so this is not a tokens/s benchmark |
| System CPU % | All 8 cores together = 100% |
| Process CPU % | One core = 100%, so multithreaded engines exceed 100% |
| System RAM | MemTotal minus MemAvailable, sampled every 250 ms |

All times are milliseconds unless noted. Medians only; no p95 figures were recorded.

### 1. NPU chat latency

| Capture | First text | Notes |
| --- | ---: | --- |
| Accepted typed voice run | 262.1 | Bypasses Whisper |
| Accepted microphone voice run | 233.7 | Full voice pipeline |
| Resource-reported voice turn A | 221.7 | 32 prompt / 83 output tokens |
| Resource-reported voice turn B | 636.7 | 134 prompt / 255 output tokens |
| Historical custom backend 0.2.2, short prompts | about 240 to 340 | Earlier project record |
| Historical stock RKLLama | about 740 to 820 | Not a matched rerun |

Longer prompts increase time to first text (turn B had about 4x the prompt tokens of turn A). The gap between the custom backend and stock RKLLama is mostly wrapper, prompt and history handling, not faster NPU decoding; the individual causes were not isolated.

### 2. Standalone Piper TTS: CPU versus Vulkan

Run `tts-runs/20261103-222700-2538`. One discarded warmup per backend, then 3 trials in alternating order. Each trial started a new process and loaded the model, so these include load time.

| Backend | Median WAV ready (incl. process + model load) | RTF |
| --- | ---: | ---: |
| CPU, 4 threads | 1223.1 | 0.282 |
| Vulkan, Mali-G610 | 4082.0 | 0.940 |

CPU was **3.34x faster**. In the Vulkan build only the Piper decoder ran on the GPU; the duration components stayed on CPU. Both backends produced correct, playable audio.

### 3. Resident overlap: Whisper + Piper + NPU together

Run `overlap-runs/20261103-233353-2885`. Speech workers resident and warmed, 5 measured rounds per backend, alternating order. Fixed fixtures reused within the run (synthetic overlap, not live mic capture during playback):

- **Whisper input:** 16 kHz PCM16 WAV, "What time does the library open tomorrow morning?"
- **TTS text:** "Hello. This is the Orange Pi speech test. The headphone output is working."
- **NPU prompt:** describe how a library helps a community in about eighty words.

| TTS backend | Stage | Whisper | TTS | NPU completion | TTS RTF |
| --- | --- | ---: | ---: | ---: | ---: |
| CPU | Whisper alone | 867.3 | | | |
| CPU | TTS alone | | 1058.8 | | 0.244 |
| CPU | Whisper + TTS | 1435.3 | 1624.4 | | 0.374 |
| CPU | NPU alone | | | 16788.2 | |
| CPU | Whisper + TTS + NPU | 2371.3 | 2778.9 | 15710.1 | 0.640 |
| Vulkan | Whisper alone | 876.5 | | | |
| Vulkan | TTS alone | | 3150.6 | | 0.726 |
| Vulkan | Whisper + TTS | 1121.6 | 3212.8 | | 0.740 |
| Vulkan | NPU alone | | | 16944.4 | |
| Vulkan | Whisper + TTS + NPU | 1615.0 | 4435.8 | 17759.3 | 1.022 |

Findings:

- **Contention cost on CPU:** running Whisper and CPU TTS together made Whisper 65% slower (867 to 1435) and TTS 53% slower (1059 to 1624). Adding the NPU on top raised both again, because tokenization, HTTP and streaming still use CPU.
- **Vulkan trade-off under full load:** Whisper 32% faster (2371 to 1615), TTS 60% slower (2779 to 4436), RTF 1.022, slightly slower than real time. CPU TTS keeps more playback margin.
- **Resident versus cold:** resident CPU TTS alone (1058.8) is only slightly faster than the cold-process figure (1223.1). Resident Vulkan TTS alone (3150.6) saves about 930 ms over cold, so GPU initialization is a large part of Vulkan's cold cost.
- NPU completion stays between 15.7 and 17.8 s throughout. Output lengths differ, so these totals do not rank NPU decoding speed.

### 4. CPU core placement

Earlier attempts using `taskset` and live affinity changes did not hold (threads later appeared allowed on all 8 cores), so those runs were discarded. The valid runner used temporary systemd services with cgroup v2 `AllowedCPUs`, tried to widen its own affinity, and confirmed the kernel kept the assigned cpuset. Each stage recorded MainPID, thread masks and cgroup membership. Limits were not exclusive reservations against other processes.

Run `affinity-runs/20261104-064601-20513`, 5 rounds, layouts rotated and stage order reversed on alternate rounds. Both speech engines used 4 threads and were warmed. The NPU service kept its own scheduling.

| Layout | Stage | Whisper | TTS | NPU completion | TTS RTF |
| --- | --- | ---: | ---: | ---: | ---: |
| Shared pool | Whisper alone | 912.3 | | | |
| Shared pool | TTS alone | | 973.7 | | 0.224 |
| Shared pool | Whisper + TTS | 1384.3 | 1540.7 | | 0.355 |
| Shared pool | NPU alone | | | 16780.3 | |
| Shared pool | Whisper + TTS + NPU | 2027.1 | 2602.9 | 16115.1 | 0.599 |
| Whisper on A76 (4-7), Piper on A55 (0-3) | Whisper alone | 880.3 | | | |
| | TTS alone | | 3729.9 | | 0.859 |
| | Whisper + TTS | 860.4 | 3721.4 | | 0.857 |
| | NPU alone | | | 16901.7 | |
| | Whisper + TTS + NPU | 1503.1 | 3969.3 | 15531.7 | 0.914 |
| Piper on A76 (4-7), Whisper on A55 (0-3) | Whisper alone | 3274.9 | | | |
| | TTS alone | | 911.3 | | 0.210 |
| | Whisper + TTS | 3344.1 | 894.6 | | 0.206 |
| | NPU alone | | | 16239.6 | |
| | Whisper + TTS + NPU | 3621.0 | 2059.5 | 15198.9 | 0.474 |

Findings:

- **A76 versus A55 single-engine cost:** Whisper takes about 3.7x longer on the A55 cluster (880 vs 3275); Piper about 4.1x longer (911 vs 3730).
- **Isolation works when not contended:** with split clusters, Whisper + TTS together are no slower than each alone, unlike the shared pool.
- **Under full load:** Whisper-fast improved ASR by 26% but TTS was 52% slower. TTS-fast improved TTS by 21% but ASR was 79% slower.
- **Shared pool is the default.** It gave the best combined result. Other thread counts, partial A76 splits and priority policies were not tested.

### 5. Clock and governor state

Snapshot of the image's defaults during testing:

| Device / policy | Governor | Allowed range | Observed |
| --- | --- | --- | --- |
| CPU policy0 (cores 0-3, A55) | schedutil | 1.2 to 1.8 GHz | |
| CPU policy4 (cores 4-5, A76) | schedutil | 0.408 to 2.304 GHz | |
| CPU policy6 (cores 6-7, A76) | schedutil | 0.408 to 2.304 GHz | |
| DMC (memory) | dmc_ondemand | 528 to 2112 MHz | 528 MHz |
| GPU | simple_ondemand | 200 to 1000 MHz | 200 MHz |
| NPU | rknpu_ondemand | 300 to 1000 MHz | 1000 MHz |

These are point-in-time snapshots, not proof of sustained clocks or absence of throttling.

**Exploratory CPU `performance` governor test** (CPU policies only; prompts and output lengths not identical):

| Metric | schedutil | performance |
| --- | ---: | ---: |
| Whisper transcription | 837.0 | 767.0 |
| AI first text | 230.1 | 150.1 |
| AI last text arrival | 22405.0 | 15077.8 |
| Client-observed decode tokens/s | 9.02 | 12.93 |
| First player after input | 6904 | 4779 |
| First chunk synthesis | 2994.5 | 2474.3 |
| First chunk audio (s) | 6.153 | 5.584 |
| Prompt / output / total tokens | 27 / 201 / 228 | 27 / 194 / 221 |
| Peak system RAM (MiB) | 4102.6 | 4212.9 |
| Peak NPU load per core % | 79 | 86 |

The tokens/s figure combines client-side text arrival with API token counts and can be affected by streaming backpressure; it is not native NPU decode speed. The large decode change suggests CPU-side work (sampling, tokenization, streaming) limits the NPU pipeline under `schedutil`, but this was not a controlled test. **This image does not change any governor.** Without a heatsink, a short-run gain does not show that maximum clocks are sustainable.

### 6. End-to-end spoken interaction

Sentence-based streaming: each finished sentence is synthesized while earlier audio plays.

| Run | Input | AI first text | First player after input | Speech chunks | Synthesis overlapped playback |
| --- | --- | ---: | ---: | ---: | --- |
| `20261104-071901-23279` | Typed question about the Orange Pi | 262.1 | 7319 | 3 | Yes |
| `20261104-071944-23331` | Microphone question about Christmas | 233.7 | 1791 | 14 | Yes |

For the microphone run, timing starts when recording stops, so the 1.8 s includes Whisper, the first answer sentence and its synthesis. The typed run's long first sentence likely explains its 7.3 s delay (inferred from reply shape, not a per-stage measurement). The tester confirmed complete speech and acceptable pauses. Capture is limited to 30 s per turn; there is no echo cancellation, wake word or barge-in.

### 7. Resource use per voice turn

| Question (as transcribed) | First text | First player | System CPU mean / peak % | Peak RAM (MiB) | NPU core 0 / 1 / 2 mean % | NPU peak per core % | Tokens prompt / output / total |
| --- | ---: | ---: | --- | ---: | --- | ---: | --- |
| Purpose of a generous break | 221.7 | 5629 | 15.37 / 55.72 | 4006.3 | 13.42 / 13.45 / 13.57 | 75 | 32 / 83 / 115 |
| Purpose of an NVME | 636.7 | 10916 | 18.10 / 58.50 | 4137.7 | 15.06 / 15.09 / 15.31 | 79 | 134 / 255 / 389 |

- Whisper and Piper each reached about 400% process CPU (4 full cores) during their stages.
- NPU load is spread evenly over all three cores. Means include recording and playback time, so they understate load during generation.
- Peak system RAM across all captured voice runs: **4006 to 4213 MiB** of 8 GB with the NPU model, Whisper, Piper and Open WebUI loaded.
- 250 ms sampling can miss short peaks. RSS sums double-count shared pages and miss accelerator allocations.

### 8. Model sizes

| Model | RKLLM file size | Status |
| --- | ---: | --- |
| Qwen2.5 1.5B Instruct W8A8 | 2,055,447,460 bytes (1.91 GiB) | Accepted baseline |
| Qwen2.5 3B Instruct W8A8 | 3,755,461,260 bytes (3.50 GiB) | Trialled; returned to 1.5B |

File size is not loaded RAM; KV cache, runtime buffers, tokenizer and the rest of the stack add to it. No controlled 1.5B versus 3B quality, RAM, heat or speed comparison was made.

### 9. Audio settings that worked

- **Capture:** `plughw:CARD=rockchipes8388,DEV=0`, stereo PCM16 at 16 kHz, channel 0 converted to mono for Whisper. Main Mic on, capture unmuted, both capture PGAs set absolutely to +18 dB with readback (repeated starts do not stack gain). No software gain. These are not applied automatically by the image.
- **Playback:** the codec accepts 48 kHz stereo PCM16. Direct 22.05 kHz mono Piper output fails with `Unable to install hw params`. An application-local ALSA `plug` device (selected with `ALSA_CONFIG_PATH`) resamples and upmixes without touching the global config:

  ```text
  </usr/share/alsa/alsa.conf>
  pcm.chatbox_tts {
      type plug
      slave {
          pcm "hw:CARD=rockchipes8388,DEV=0"
          format S16_LE
          rate 48000
          channels 2
      }
  }
  ```

### 10. GPU feature notes

- Numeric OpenCL (Rusticl) and Vulkan (PanVK) checks passed on the Mali-G610.
- Vulkan device properties report **FP16**. BF16 and matrix/cooperative cores are not reported. OpenCL FP16 was not separately established.
- Rusticl only exposes the GPU with `RUSTICL_ENABLE=panfrost`. Login shells get it; systemd services and containers must set it themselves.
- Passing enumeration and numeric checks does not mean an application uses the GPU or speeds up. Piper on Vulkan is the only workload measured so far, and it was slower.

### 11. Lessons from building on the board

- A large native build (audio.cpp Vulkan shaders) stalled the Pi and froze another SSH session; a power cycle was needed. Resource pressure is suspected; no OOM or thermal log confirmed it. This recovery worked:

  ```sh
  docker stop chatbox-webui
  systemctl stop chatbox-npu-http
  cmake --build <build-dir> --target audiocpp_cli --parallel 1
  ```

  Then restart the services. Build serially on the 8 GB board while AI services are stopped.
- Docker needs kernel options this image enables explicitly (overlayfs, namespaces, seccomp, cgroups/memory/pids/cpusets, BPF, NAT). Check the live kernel with `chatbox-status --containers`.
- `curl` is not installed; use Python's standard library for HTTP health checks. A 200 health response is not proof the model generates output.
- Some NPU, regulator/OPP, OP-TEE and SCMI boot warnings remain in the kernel log. Inference works regardless, but the warnings are not resolved.

### 12. What has not been measured

| Item | Status |
| --- | --- |
| Idle or loaded SoC temperature | Not recorded |
| Thermal equilibrium time | Not measured |
| Thermal throttling | Not established |
| Board or wall power | Not measured |
| Heat-related crash or shutdown | None established |
| whisper.cpp on Vulkan | Not tested |
| MLC-LLM on Rusticl | Not tested |
| Long sessions, memory pressure, repeated reboots | Not tested |

Missing measurements are missing, not zero. The full report includes a read-only telemetry collector (thermal zones, trip points, cooling states, CPU/devfreq clocks, memory, NPU load) and a step-by-step no-heatsink measurement protocol for anyone who wants to contribute thermal data.

The full report, with methods, qualifications and the telemetry script, is in [`docs/COMMUNITY-TEST-REPORT-2026-11-06.md`](docs/COMMUNITY-TEST-REPORT-2026-11-06.md).

## Recovery kernel

A stock Debian `6.12.113+deb13-arm64` kernel and DTB are included on the image. Select it for the next boot with `chatbox-select-kernel recovery`, and return with `chatbox-select-kernel display`. Do not mix kernel, DTB, firmware or libmali files from 1.9.0 images into this one.

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
- [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md): hardware acceptance gates
- [`docs/LOCAL-VERIFICATION.md`](docs/LOCAL-VERIFICATION.md): verification performed and its limits
- [`docs/COMMUNITY-TEST-REPORT-2026-11-06.md`](docs/COMMUNITY-TEST-REPORT-2026-11-06.md): real hardware benchmarks, failures and thermal test protocol

## Third-party components

This repository contains source and build scripts only. It does not include any OS image, compiled kernel, firmware binary, Debian package or model. All of these are downloaded and verified at build time from their upstream sources, including:

- Debian Trixie ARM64 root from [johang/sd-card-images](https://github.com/johang/sd-card-images)
- [Armbian linux-rockchip](https://github.com/armbian/linux-rockchip) kernel source (GPL-2.0)
- Mesa PanVK, Rusticl, Linux firmware and supporting packages from the Debian archive
- [Rockchip RKLLM](https://github.com/airockchip/rknn-llm) runtime

Each component remains under its own license. Debian package licences are installed under `/usr/share/doc` in the resulting image. If you redistribute a built image, you are responsible for providing corresponding kernel source as required by the GPL.

## License

The Chatbox build scripts, overlay files, tools and documentation in this repository are released under the [MIT License](LICENSE).

The MIT License covers only this project's own work. Components downloaded at build time (kernel, Debian packages, Mesa, firmware, RKLLM and any models) keep their own licenses.

## Credits

Hands-on testing, project direction and integration: **Matthew Kinderwater**, ICUBEDEV CGY ([icubedev.com](https://icubedev.com)), Calgary, Alberta. AI assistance was used in code iteration and report preparation.

The engines, models, drivers and UI used in testing remain the work of their authors: Orange Pi and Rockchip, Linux and Armbian, Mesa, Rockchip rknn-llm, the GatekeeperZA RKLLM model conversion and API server, Qwen, whisper.cpp and OpenAI Whisper, audio.cpp and Piper voice authors, Open WebUI, Sentence Transformers and spaCy. This project assembles, configures, tests and diagnoses them.
