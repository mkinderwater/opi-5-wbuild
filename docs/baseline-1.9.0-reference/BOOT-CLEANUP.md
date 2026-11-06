# Boot cleanup and checker corrections

This release pauses AI-engine integration and addresses the supplied boot log,
status JSON and actual sysfs driver mapping from the original Orange Pi 5.

## Corrections included

| Observation | Correction | Validation boundary |
|---|---|---|
| Actual NPU driver is RKNPU, not lowercase rknpu | Both checkers compare names without case sensitivity | Registration is still not inference proof |
| Mali400 loads on this G610 board | Set CONFIG_MALI400 off and reject configs that enable it | New kernel required; rmmod cannot remove the current built-in driver |
| LED pinctrl requests GPIO0_A2 while the LED GPIO uses GPIO1_A2 | Override leds_gpio pinctrl to bank 1, matching the GPIO property | Compiled DTB validated; physical heartbeat and conflict resolution need board testing |
| GPU power-off-delay-ms missing | Set 200 ms, exactly the pinned platform driver's existing fallback | Repeat OpenCL computation; no intended timing change |
| regulatory.db missing | Pin Debian wireless-regdb, resolve alternatives into the initramfs and verify database/signature presence | Verify early load and signature acceptance on the board |

The broad Rockchip defconfig explicitly selected CONFIG_MALI400=y. Earlier
fragments selected Valhall but did not override that unrelated built-in driver.
Mali400 serves Mali-300/400/450 hardware, not this board's Mali-G610. This is a
specific GPU correction requested for this board, not general driver pruning.
Wi-Fi/Bluetooth and other hardware capabilities retain upstream defaults.

Local overrides are in inputs/board-fixes.dtsi. They are copied into freshly
verified source and included only by the original Pi 5 DTS. The resulting DTB
is validated for matching LED GPIO, pinmux and phandles. The input hash is
recorded and the override is included in kernel package documentation. Existing
SPI firmware and bootloader are untouched.

The regulatory package is 2026.05.30-1~deb13u1, SHA-256
72048ee2f369a8c2df8b5f99f79489d3812d869282038cfe55e23a4748231399.
It is data for retained wireless support, not a Wi-Fi module requirement.
Final initramfs regeneration runs after all packages are configured so Debian's
firmware alternatives are ready. The build checks both early firmware files.

## Warnings left visible

| Warning | Evidence and action |
|---|---|
| NPU register regions busy | The pinned driver explicitly falls back from devm_ioremap_resource to devm_ioremap on EBUSY. The supplied log then initializes RKNPU 0.9.8. Do not remove reservations or bypass checks; inference is still untested. |
| VOP/video-encoder OPP regulators missing | Some supplies are absent from the board DTS. Choosing by regulator name alone can change voltage on a shared rail. No supply changes without confirmed wiring and power-domain constraints. |
| OP-TEE API UID mismatch, SCMI protocol 17 unavailable | Need comparison against installed secure/SPI firmware. No speculative firmware replacement or disabling subsystems. |
| GPU revision fallback and timeout caps | Driver reports proceeding normally; prior OpenCL computation passed. Preserve hardware identity and checks; repeat on the new kernel. |
| Duplicate debugfs and camera/codec messages | Keep diagnostics; do not disable subsystems to reduce log noise. |
| Earlier NVMe timeout | Later boot has working queues, mounted root and successful expansion. No evidence identifies a specific power-management fix. Repeat cold boots and retain any recurrence. |

Status reports selected categories from dmesg --level=err,warn, as counts only.
Missing permission and truncated output are explicit. This is not a complete
kernel health verdict. Historical messages remain visible even if a later
probe succeeds. The checker never clears the kernel log.

## Apply checker correction to 0.1.7 now

From PowerShell in the extracted 1.9.0 source directory:

```powershell
scp .\overlay\usr\local\lib\chatbox\board_report.py root@BOARD_IP:/usr/local/lib/chatbox/
scp .\overlay\usr\local\lib\chatbox\acceptance.py root@BOARD_IP:/usr/local/lib/chatbox/
scp .\overlay\usr\local\sbin\chatbox-status root@BOARD_IP:/usr/local/sbin/
scp .\overlay\usr\local\sbin\chatbox-hardware-check root@BOARD_IP:/usr/local/sbin/
ssh root@BOARD_IP "chmod 755 /usr/local/sbin/chatbox-status /usr/local/sbin/chatbox-hardware-check"
ssh root@BOARD_IP chatbox-status
```

The image still reports 0.1.7. Its old kernel is correctly flagged for legacy
Mali400, and existing boot warnings remain visible. Copying checkers does not
install kernel/DT/firmware corrections. Full cleanup uses the normal fresh
.\Build.ps1 build and newly flashed NVMe image.

## New-image acceptance

1. Confirm uname -r is 6.1.172-chatbox4-arm64 and root is on NVMe.
2. Confirm services, SSH and visible HDMI remain healthy.
3. Retain chatbox-status --compute --json output and the full boot log.
4. Confirm NPU recognition and numerical GPU computation. Render node numbers
   need not remain constant; do not assume renderD129 forever.
5. Confirm the heartbeat LED works without GPIO0_A2 conflicts; no Mali400 load
   message or missing GPU delay/regulatory database warning.
6. Repeat microphone capture/playback, followed later by actual RKLLM inference.
7. Perform at least three cold boots and three warm reboots to watch for the
   earlier NVMe timeout. Capture recurrence before changing parameters.

Primary evidence: pinned rockchip_linux_defconfig, Mali400 Kconfig, original
Pi 5 DTS, Valhall platform/rk/mali_kbase_config_rk.c and rknpu_drv.c:
https://github.com/armbian/linux-rockchip/tree/85233a85b67928000afc2e966bab86a8c414f1b4
