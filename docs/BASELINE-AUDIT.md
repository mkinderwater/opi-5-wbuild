# Baseline audit: 2.0.1 GPU experiment

## Authoritative starting point

This release was created from Matthew's attached `chatbox-image-1.9.0-source(1).zip`, rather than the 1.9.2 tree used for the superseded 2.0.0 experiment. The new version and kernel suffix distinguish the two candidates.

Attachment SHA256: `8a0c7dad2ac1c2e9717f00bdb199c325b6bb9deb4009c72bcb902962a3c674f3`.

## Preserved behavior

The following files are byte-identical to the attached baseline:

| File | SHA256 |
| --- | --- |
| `Build.ps1` | `4a0e0ed1cf9872fba65e555f26b0ded8c34419b0a715940cff145eaed70635d6` |
| `build.sh` | `87c1b9f84669b4e7a2ef6b7b4ae02bcac53764d5d15246be29c7a668756f3d24` |
| `scripts/offline.py` | `e13b68848d6de42300d6cd3b96737478767b8b1aff5726dcecf043fff872c1ca` |
| `scripts/prepare_login_accounts.py` | `0794af02fa8c63889253d610ed6cf3648c892a6c71f8f07d4b8eb4fa8c692fee` |
| `scripts/make_fat32.py` | `99e91f247535ec67304463ca40de8d1ee6a38842b78d4e4efbc71cc3fc015f9e` |
| `CONFIG.TXT` | `41fbcd24b45fdb003b5cb636f2621d58f24956f29d1e9f3daeb657743984c8a4` |

The Windows entry script changes release, output and fresh-workspace labels only. The baseline boot/provisioning/offline preparation flow remains intact. NVMe layout, Ethernet DHCP, CONFIG.TXT provisioning, account preparation and expansion remain the baseline design. The pinned kernel source commit/archive and RKLLM runtime are retained. Baseline documents are copied verbatim into `docs/baseline-1.9.0-reference/`.

## Intentional changes

- Replace proprietary Valhall/libmali with the source tree's existing Panthor backport and pinned Mesa PanVK/Rusticl packages. Add matching CSF firmware, GPU regulator and thermal-map links, initramfs inclusion and package asset validation.
- Carry forward explicit Docker kernel requirements and functional container diagnostics: overlay2, namespaces, cgroups, bridge/veth, NAT/nftables and seccomp. These are intentional requirements for the established Open WebUI deployment, beyond a GPU-only change.
- Add explicit MAX98357A module support for the planned amplifier. Preserve baseline codec support.
- Add numeric Vulkan and OpenCL diagnostics, hardware identity checks, pinned GPU package dependency closure, runtime library checks and release metadata. Increase root staging allowance to accommodate that closure.
- Add host glslang-tools for shader compilation. Both GPU APIs and all runtime assets are staged before boot.
- Relabel kernel ABI as `6.1.172-chatbox8-arm64` and package version as `6.1.172-1+chatbox8` to distinguish this build.
- Omit historical custom application installers. Stock AI applications are installed separately after platform acceptance.

The GPU implementation was selectively carried from 2.0.0. Later generic platform-profile, RTC/watchdog/ramoops and PSI gates were removed from this rebase. No unrelated expansion of those requirements is part of this candidate. GPU ownership changes are necessary for this experiment; the release does not generally disable absent Wi-Fi/Bluetooth hardware support.

## Verification and acceptance

105 host tests passed; three skipped (108 discovered). Real pinned DTS compilation and validation, shader SPIR-V validation and checker compilation were performed. Full kernel compilation, QEMU image assembly and hardware boot were not performed here. See `LOCAL-VERIFICATION.md` for exact limits and `ACCEPTANCE.md` for board checks.

Keep the working 1.9.0 NVMe as rollback. Test 2.0.1 on a separate drive. Existing libmali-mounted MLC containers are not compatible unchanged with Mesa. Numeric API checks must pass first, followed by NPU inference and application-level Whisper Vulkan evaluation. No cooling or clock-policy change is imposed.
