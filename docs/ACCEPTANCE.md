# Acceptance and rollback

This image is experimental. Keep the proven NVMe untouched and boot a separate test NVMe using the existing SPI bootloader. Rollback is swapping back to the proven drive. Do not mix kernel, DTB, firmware or proprietary libmali assets from the two images. No SPI rewrite is part of this release.

## Gate 1: Boot and registration

Expect uname -r = 6.1.172-chatbox8-arm64. Verify Ethernet DHCP, SSH provisioning, NVMe root/expansion, visible HDMI, onboard ES8388 capture, GPIO/I2C/SPI availability as routed, no failed units, container prerequisites and NPU render-node ownership. Check render drivers through /sys/class/drm/renderD*/device/driver. Do not assume the old renderD129 index belongs to the NPU after adding a GPU DRM driver; use actual driver identity.

## Gate 2: Both GPU APIs

Run chatbox-status --vet --compute --json. OpenCL and Vulkan must each report independent numeric passes on hardware Mali-G610. Software llvmpipe/lavapipe is not acceptable. Review full clinfo and vulkaninfo for available extensions/features. Numeric arithmetic checks are diagnostics, not model benchmarks. An API missing necessary fp16/subgroup/storage features can pass simple arithmetic and still fail MLC/Whisper.

## Gate 3: Preserve NPU and audio

Install/run the unchanged stock RKLLama deployment and verified model. Confirm real generation and repeat the same baseline workload. Mount devices by driver identity and grant matching render/video/DMA-heap permissions; NPU node numbers may change. Verify Docker overlay2, networking, cgroup limits and seccomp using the existing container test. Record onboard mic at the validated 18 dB gain, channel 0; these measured application settings are not silently applied to a newly imaged system. Confirm mixer persistence after reboot and speaker/amp routing separately.

## Gate 4: Application acceleration

Build stock whisper.cpp from the same pinned source for CPU and Vulkan, using identical models, decoding and WAV fixtures. The Vulkan build requires its supported compiler/toolchain; build-time detection and actual GPU execution logs are mandatory. Keep original CPU recordings unchanged. Test separately, then alongside NPU generation.

MLC's existing container image was built around proprietary libmali mounting. It cannot simply be pointed at Rusticl without a matching Mesa dependency environment. Use a new compatible native/container userspace profile, retain its source/model pins and verify fp16 and workload execution. Do not claim prior OpenCL application performance persists across this driver switch.

## Gate 5: Sustained appliance operation

Run repeated cold boots and warm reboots, clean shutdown/recovery, long conversations and concurrent ASR/LLM/TTS workloads. No added cooling is the present test condition; record starting temperatures and clocks without a forced cooldown gate. Compare median/p90 over at least ten repetitions, quality, memory, swap and endpoint-to-first-audio. Record input power with a meter when available. Do not infer throttling from a temperature maximum alone.

Promotion requires NPU preservation, both APIs and meaningful application benefit. A newer/more open graphics stack is not automatically faster. If a gate fails, retain the complete logs and use the proven drive. Missing firmware, Mesa feature support and backport compatibility must be distinguished before changing more components.
