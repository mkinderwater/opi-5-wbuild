# Chatbox 1.9.0 platform baseline

## Target and rules

Original Orange Pi 5, 8 GB, no onboard Wi-Fi/Bluetooth module, Ethernet DHCP,
working SPI bootloader and NVMe. Windows PowerShell invokes Debian WSL2. Build
from source with fresh verified downloads and a new full kernel compile every
time. No cache, incremental reuse, resume or precompiled image delivery.

Keep CONFIG.TXT to ROOT_PASSWORD, TIMEZONE and HOSTNAME only. A nonempty root
password has no arbitrary minimum length. Preserve identities, SSH provisioning,
root expansion, diagnostics and recovery. Do not prune unrelated drivers because
the board lacks an optional module. The specific obsolete Mali400 exclusion is
an authorized G610 correction. Do not change SPI or voltage rails speculatively.

## Included stack

| Component | Choice |
|---|---|
| Base | Pinned Johang Debian Trixie ARM64 root |
| Kernel | Pinned Rockchip 6.1.172 source; ABI 6.1.172-chatbox4-arm64 |
| Boot/root | Matched kernel, DTB, modules and initramfs prepared before flashing; NVMe PARTUUID |
| GPU | Valhall g29p1-11eac0, matching embedded firmware, OpenCL-only g29p1-11eac1 userspace and Debian ICD loader |
| NPU | RKNPU 0.9.8 and RKLLM 1.2.3 runtime, no model |
| Audio | ES8388 through vendor ES8323 driver, ALSA |
| THP/tuning | madvise; no forced clocks, IRQ, swap or storage tuning |
| Application | Loopback-only text coordinator, diagnostics and enhanced status checker |
| Regulatory DB | Pinned Debian package's upstream-signed alternative, matching kernel wens key |
| Recovery | Retained Debian 6.12 kernel; existing SPI untouched |

The hardware lock remains the authority for commits, versions and hashes. MPP
metadata now uses a command-line revision label derived from the pinned source
commit. It is provenance for an archive, not a claim that Git history is present.
The MPP Makefile's immediate revision assignment is made conditional so its Git
shell expression is not evaluated. The patched Makefile hash and revision label
are recorded in build provenance. Driver functionality and kernel ABI are unchanged.

## Evidence obtained on the preceding 1.8.2 stack

- Correct chatbox4 kernel booted with NVMe root and successful expansion to 235 GB.
- No failed systemd units; SSH, network and coordinator running; NTP synchronized.
- HDMI console visible; 1920x1080 at 60 Hz reported in the boot log.
- Mali-G610 OpenCL kernel compiled, executed and returned correct numeric results,
  including a direct user-run timeout 60 chatbox-opencl-check PASS.
- Installed GPU firmware/runtime hashes matched recorded provenance.
- Legacy Mali400 absent; live LED mapping matched GPIO1_A2 and conflict disappeared.
- Live GPU power-off delay matched the driver's existing 200 ms fallback.
- RKNPU 0.9.8 registered under uppercase RKNPU and was correctly detected.
- Onboard codec registered, approximately 35-36 C in one status snapshot, ample RAM.

These observations establish basic behavior of that board/stack, not sustained
performance, audio quality, inference, electrical pin validation or every boot.
They are not automatically a physical acceptance result for the new 1.9.0 image.

## Regulatory corrections and remaining confirmation

The initramfs hook originally mishandled Debian copy_file return 1 for an
already-copied file. It now verifies identical bytes before accepting that code
and still rejects actual errors. Tests use Debian's real helper function.

The subsequent boot exposed a signer mismatch: Debian's default alternative was
signed by the Debian maintainer, while the vendor kernel trusts upstream keys.
The upstream signature was cryptographically checked against the wens certificate
from the pinned kernel; the DB header also matches the kernel's format version.
Build policy now selects both upstream files and regenerates the final initramfs.
The checker catches the exact malformed/signature rejection message and checks
alternative selection. Post-repair reboot evidence has not yet been supplied.
Do not mark signature acceptance passed solely because files exist.

## Warnings and boundaries

| Item | Status |
|---|---|
| NPU busy register regions | Vendor fallback followed by successful registration; inference still required |
| VOP/video-encoder OPP regulators | Unresolved board/driver power-management definitions; no speculative supply changes |
| OP-TEE UID mismatch / SCMI protocol 17 | Unresolved secure-firmware interfaces; no SPI update |
| Ethernet 100 Mbps | Operational but below gigabit; inspect cable/port negotiation separately |
| GPU firmware loading, timeout caps and cache flag adjustment | Setup/workaround messages in pinned driver; basic computation passed; not evidence of an elapsed timeout or actual MMA fault |
| Duplicate debugfs / camera-codec diagnostics | Retained for investigation; not hidden by disabling subsystems |
| Earlier NVMe timeout | Absent from subsequent supplied boots; cause not established; repeated cold/warm boots still required |
| Optional Realtek Bluetooth firmware warnings during build | Not the fatal initramfs error; board has no BT module, optional adapter firmware may be needed later |
| SPI/I2C peripheral nodes absent | Capability compiled; OLED/controller/pinmux and device integration remain unresolved |

Kernel warnings can print over tty1's login prompt. Press Enter to redraw it;
the display is not necessarily frozen. Do not suppress all warnings to conceal
issues. Actual GPU resets/faults, failed computation or recurrent NVMe timeouts
require investigation.

## 1.9.0 acceptance and next AI work

After the user's fresh WSL build and NVMe flash, confirm 1.9.0 metadata and the
chatbox4 kernel, then run chatbox-status --vet --compute --json and retain dmesg.
Verify upstream regulatory selection and absence of signature rejection on the
new boot. Confirm the physical LED and HDMI, and perform repeated cold/warm boots.
Keep the known-good recovery route and collect logs before changing parameters.

Next AI milestone is a real RKLLM 1.2.3-compatible model inference through a
restricted local worker. Compare a small CPU llama.cpp baseline on this board
before selecting the default. Then prove microphone capture/playback, persist
mixer settings, select streaming ASR and Piper assets, and connect the basic
turn-taking voice loop. Do not assume RKLLama's current runtime/Python versions
match this image or auto-load multiple models.

Browser authentication/settings, physical-button enable/disable persistence,
OLED integration, optional explicit memory and timers remain application work.
Wake words and interruption are later scoped features. No model or engine is
silently added by this baseline release. Use the existing alignment/test plan
for latency, quality, privacy, recovery and sustained-load acceptance.
