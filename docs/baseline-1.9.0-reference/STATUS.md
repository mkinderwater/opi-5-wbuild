# Status inspection

Checker revision 1.9.0 adds an explicit acceptance pass for image 1.9.0:

```bash
chatbox-status --vet --compute --json > /tmp/chatbox-status.json
```

`--vet` is read only. It verifies the expected image/kernel target, live LED
GPIO/pinctrl phandles, live 200 ms GPU delay, nonempty matched boot assets,
regulatory signature and early initramfs firmware entries, firmware/runtime
hashes against local build provenance, all failed units, actual NTP sync,
physical Ethernet link speed, and root partition/filesystem expansion.
Local provenance is a consistency check, not independent attestation. Hashing
the firmware copy does not prove the embedded driver's firmware bytes match.
Initramfs listings can time out or truncate; those results remain unknown.

The regulatory signing-variant check requires the upstream database and paired
signature for this vendor kernel. File presence alone does not establish trust.
The boot scan detects malformed/invalid/rejected signatures, including the exact
message previously missed. See REGDB-FIX.md for the signer correction.

Vetting expects the project's single-root NVMe layout and allows up to 256 MiB
outside root for config/alignment. Filesystem capacity must cover at least 90%
of its partition. Different layouts need manual review. A 100 Mbps link is a
warning, not proof of a defective NIC. An unsynchronized clock can be temporary.

Reports identify the checker revision separately from image release, summarize
the baseline as blocked/review-required/checks-passed, and list remaining tests.
Even checks-passed does not establish microphone, NPU inference, physical LED,
reboot reliability, recovery or sustained-load acceptance. Reports are not
persisted automatically and no prior test pass is carried into a new run.

The full 1.9.0 builder installs the checker automatically. The diagnostic-only
installer at scripts/install-checker.sh is also included. Copying diagnostics
onto an older image does not upgrade it: the 1.9.0 acceptance target will fail.

Run on the Orange Pi:

```bash
chatbox-status
chatbox-status --json > /tmp/chatbox-status.json
```

Run as root for the fullest visibility. Unknown means insufficient evidence,
not disabled. The command does not change configuration, start or stop services,
mount debugfs, load modules, tune clocks, record/play audio or run inference.
It does make loopback-only GET requests to the coordinator's health and ready
endpoints; the latter asks the configured engine for its advertised models.
No requests go directly to external services.

Each row distinguishes installed files, application configuration, enablement,
runtime state and functional testing. Most cells are intentionally unknown or
not-run when the observation cannot establish them. Installed means file or
unit presence, not a successful dependency load. Kernel enablement is y/m
support, not a loaded module. Built-in drivers need not appear in lsmod.

The report checks:

- Expected versus running kernel ABI, kernel config and NVMe root source.
- Kernel capabilities for HDMI, ES8388 audio, USB audio, GPU, NPU, GPIO, SPI and I2C.
- Live device-tree GPU/NPU enablement, driver registration and device nodes.
- Firmware inspection copy, RKLLM/Mali libraries, OpenCL loader and ICD configuration.
- Boot enablement separately from activity for provisioning, readiness, coordinator,
  SSH, networking and time synchronization services.
- Provisioning marker, audio registration, HDMI connector state and caller access
  to GPIO/SPI/I2C device nodes.
- Valid coordinator configuration, API liveness and advertised model readiness.
- Legacy Mali400 enablement, regulatory database presence and selected boot
  warning counts. NPU driver names are matched without case sensitivity.

The firmware inspection copy is not proof that the driver initialized firmware.
HDMI connected is not proof of a visible image. NVMe root source is not proof
that expansion used the entire drive. A provisioned marker is not a credential
test. Model advertisement is not inference. Device-node permissions describe
the caller, not the eventual restricted worker account.

The status command describes the application integration supplied by this
release. Independently installed third-party voice/browser/button/OLED programs
are outside its inventory. It does not scan arbitrary directories for model
files or claim such files work just because they exist.

## Explicit functional test

```bash
chatbox-status --compute
chatbox-status --compute --json > /tmp/chatbox-status.json
```

This runs the existing OpenCL checker with a 65-second timeout, compiling and
executing a numerical GPU kernel. It marks only this invocation's GPU execution
as pass/fail/timeout/unavailable. It does not persist a pass for future runs or
establish a working AI model. Do not run during a latency benchmark.

Audio, NPU inference, GPIO wiring and the full speech conversation still need
the procedures in HARDWARE-TESTS.md and ALIGNMENT-AND-TEST-PLAN.md. Overall
hardware acceptance remains not established even if all inventory rows look good.

## Results

- OK: the stated observation agrees with expectations. Check the Tested column.
- INFO: capability or state reported without treating it as a failure.
- WARN: incomplete evidence, optional connectivity, or a service state to inspect.
- FAIL: explicit mismatch, missing required artifact, disabled required capability,
  failed/missing service or a requested computation that did not pass.

An unconfigured model backend is expected on a fresh image and is not a failure.
Exit code 0 means no explicit FAIL rows; 1 means one or more FAIL rows. Warnings
do not change the exit code. Neither code is a whole-device acceptance verdict.
Command output suppresses application config contents, credentials, model names,
raw journals and recordings. Inspect reports before sharing them.

## Diagnostic-only installation

The full image build installs all diagnostic files automatically. No separate
checker package is needed. The source also contains scripts/install-checker.sh
for an existing compatible Chatbox Python/coordinator installation. Copy the
source folder to the board and run that script as root to update diagnostics
only. The image/kernel release is unchanged by this action. The explicit
1.9.0 vetting target will fail on an older image until it is actually upgraded.
