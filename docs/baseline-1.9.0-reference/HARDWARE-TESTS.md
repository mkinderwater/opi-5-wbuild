# Board acceptance checks

Boot the newly built NVMe image with Ethernet. Keep the known-good SD image for
recovery. Do not change the working SPI bootloader as part of these checks.

Follow the acceptance gates and performance protocol in ALIGNMENT-AND-TEST-PLAN.md.
Save baseline evidence before any tuning:

```bash
chatbox-status
chatbox-status --json > /tmp/chatbox-status.json
chatbox-board-report > /tmp/chatbox-board-report.json
```

See STATUS.md for enablement versus runtime versus functional-test semantics.
`chatbox-status --compute` optionally runs the existing OpenCL checker.

Copy it to Windows from PowerShell while the board is reachable:

```powershell
scp root@BOARD_IP:/tmp/chatbox-board-report.json .
```

The report does not read CONFIG.TXT, application settings, password files,
private keys, journals or recordings. It excludes unique release identifiers.
Missing or restricted fields remain null or carry an error; exit status zero
only means JSON collection finished. Device permissions describe the caller,
not a future inference worker. Connected HDMI is not proof of visible output.
No settings change, model load, recording or GPU computation is triggered.
Each external query has a three-second timeout. Run as root for fuller driver
visibility, then repeat under the eventual worker account during integration.
Inspect the evidence before sharing it. The report is separate from chatbox-diag,
which performs the OpenCL test and includes network and journal information.

## Platform

```bash
uname -r
findmnt /
df -h /
systemctl status chatbox-firstboot chatbox-readiness --no-pager
ls -l /dev/dri /sys/class/drm
chatbox-hardware-check
```

Expect 6.1.172-chatbox4-arm64, NVMe p2 root, expanded capacity, working SSH and
HDMI console. Registration checks must find an ES8388 sound card, RKNPU 0.9.8
and an RKNPU render device. Driver failure details:

```bash
dmesg | grep -Ei 'rknpu|iommu|es8323|es8388|asoc|i2s|drm|vop|hdmi'
```

If debugfs is not mounted:

```bash
mount -t debugfs debugfs /sys/kernel/debug
cat /sys/kernel/debug/rknpu/version
```

Vendor serial diagnostics use ttyFIQ0 at 1,500,000 baud; the retained mainline
recovery entry uses ttyS2. HDMI remains the visible text console.

## Microphone and jack

```bash
aplay -l
arecord -l
cat /proc/asound/cards
```

Select the onboard codec card, not HDMI. Card numbers may change. Use its
reported card ID below in place of CARD_ID. Inspect controls and set capture
source/gain and headphone volume conservatively using alsamixer. This revision
does not impose an unverified mixer state or automatically play sounds.

```bash
alsamixer -c CARD_ID
amixer -c CARD_ID contents
arecord -D plughw:CARD=CARD_ID,DEV=0 -f S16_LE -r 16000 -c 2 -d 5 /tmp/chatbox-mic.wav
aplay -D plughw:CARD=CARD_ID,DEV=0 /tmp/chatbox-mic.wav
rm /tmp/chatbox-mic.wav
alsactl store
```

Use headphones or a powered amplifier connected to the jack. A passive speaker
requires an amplifier. Record a spoken phrase, confirm intelligibility and
check for clipping/noise. Test the actual intended microphone separately from
headset capture. Do not conclude capture works from card registration alone.

## Mali-G610 OpenCL

```bash
ls -l /dev/mali* /dev/dma_heap/
dmesg | grep -Ei 'mali|valhall|csf|gpu|firmware'
clinfo -l
timeout 60 chatbox-opencl-check
```

Expect the Mali-G610 GPU and a PASS stating that an OpenCL kernel was compiled,
executed and its results verified. Merely listing a platform, resolving shared
libraries or finding a CPU OpenCL device is insufficient. The checker rejects
CPU-only devices and wrong numerical output, including NaN.

No OpenCL check is run under build-time QEMU. It requires the physical GPU.
The matching firmware is embedded in the driver; a copy is at
/usr/lib/firmware/g29p1-11eac0.mali_csffw.bin for hash inspection.
The vendor OpenCL ICD uses /usr/lib/aarch64-linux-gnu/libmali.so.1 through the
Debian loader, without replacing the loader with a direct Mali symlink.

Test first as root over SSH. A future application account should join the
render group; udev grants that group compute-device and DMA-heap access.
Repeat the computation after a reboot and under sustained use. Record kernel
and driver versions, temperature and any faults. Then test the intended MLC or
other OpenCL workload separately; the simple probe is not a model benchmark.

## NPU

```bash
cat /sys/kernel/debug/rknpu/version
/lib/ld-linux-aarch64.so.1 --list /usr/lib/aarch64-linux-gnu/librkllmrt.so
```

The driver must report v0.9.8. The runtime must resolve libgomp, libstdc++,
libgcc and libc from the ARM64 root. chatbox-hardware-check also verifies the
render node belongs to the rknpu driver, not just to the display controller.

Final acceptance requires an RK3588-targeted model converted for RKLLM 1.2.3,
using the demo/API from Rockchip's pinned release-v1.2.3 source. No model is
bundled or downloaded automatically. GGUF/llama.cpp files are not RKLLM models.

Source: https://github.com/airockchip/rknn-llm/tree/f7df8e5de9b40dc7aaa66194cf14d4895aaf159a

Run a short prompt and confirm runtime version/driver initialization, valid
output and rising NPU utilization in /sys/kernel/debug/rknpu/load while
inference runs. Repeat several turns, checking memory and temperature. Measure
prefill and tokens/sec rather than inferring performance from the 6 TOPS label.
Only a successful real inference establishes NPU functionality.

## THP and local coordinator

```bash
cat /sys/kernel/mm/transparent_hugepage/enabled
systemctl status chatbox-app --no-pager
chatbox-api health
chatbox-api ready
chatbox-metrics
```

Expect the compiled THP default `always [madvise] never`. The coordinator should
be live on loopback only; /ready is intentionally unconfigured until an actual
engine is installed and selected. No model is auto-downloaded or warmed.
See COORDINATOR.md before configuring backend profiles. A model listing alone
is not proof of working inference; run an actual prompt on the intended engine.
