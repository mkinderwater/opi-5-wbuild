# Validation: 1.9.0

## Release scope

This release consolidates 1.8.2 and both regulatory fixes, updates the complete
builder/checker naming to 1.9.0 and supplies an explicit pinned MPP revision label.
The MPP Makefile metadata assignment is changed from immediate to conditional
so its Git shell expression is not evaluated when that label is provided.
No kernel fragment, DT override, firmware/runtime/package pins or kernel ABI
changes are introduced. A production build still downloads fresh inputs and
compiles in an empty workspace. No precompiled OS image is supplied.

Physical results from the prior stack and outstanding acceptance boundaries are
recorded in BASELINE.md. 1.9.0 itself still needs a complete WSL image build and
board boot. The regulatory signer repair's post-reboot result remains pending.

The complete 1.9.0 regression suite passed 102 tests without skips, with verified
OpenCL-header and pinned-kernel fixtures. A focused follow-up compiled the MPP
version macro using the actual vendor Makefile flags and verified the pinned
label without any Git call. The clean kernel configuration path also passed.
This does not claim a full Image/modules compile or mounted-root OS build here.

## Prior verification record: 1.8.2


## Full source release

Regulatory signer correction: source/package inspection and an OpenSSL signature
check established that the selected Debian signer differs from the vendor
kernel's upstream wens key. Build policy now selects the upstream master/slave
pair. New tests cover real private-directory update-alternatives behavior and
the exact previously missed kernel rejection message. No new kernel compile
is required for the live repair; new-board reboot acceptance remains pending.

The signer-correction full regression run passed 100 tests without skips.
Five focused selection/repair tests also passed after adding version/kernel
guards. These validate helper behavior and safe refusal; actual board initramfs
regeneration and next boot still require user execution.

Build correction: Debian copy_file returns 1 for an existing destination. The
original hook treated that result as fatal under set -e. The corrected hook
accepts return 1 only when existing firmware bytes match the source, preserves
other error codes and rejects conflicting copies. Tests execute the actual
Debian 0.148.4 copy_file function, not the former simplified stub, with new,
duplicate, partial, mismatched and failed copy scenarios. This changes an
initramfs input hook, not the kernel fragment, source, DTB override or ABI.

The original hook's exit-1 failure was reproduced with already copied firmware;
the fixed hook passed against the same files. The corrected full regression
suite passed 96 tests with no skips. The full WSL image transaction still needs
the user's fresh build; these tests do not claim that transaction was executed.

Realtek Bluetooth missing-firmware warnings are independent of this fatal hook
failure. Retained support for optional adapters is not disabled to hide them.

1.8.2 packages the complete fresh-build image builder, hardware cleanup and
enhanced acceptance checker together. Image metadata, Windows workspace/output
names, CLI checker revision and acceptance target all identify 1.8.2.
The checker remains installed automatically by full image assembly.

The complete 1.8.2 regression suite passed: 92 tests, no skips, including the
OpenCL-header and clean kernel-configuration fixtures, release/output behavior,
enhanced acceptance checks and diagnostic-only installer tests. Shell entrypoint
syntax and source-package contents are checked separately before publication.

Kernel ABI remains 6.1.172-chatbox4-arm64: no kernel source, fragment, DT override,
firmware, runtime or package input changes from the completed 0.1.8 cleanup.
Every user build still downloads fresh inputs and recompiles in an empty object
directory. No cache, precompiled kernel or OS image is supplied.

A complete WSL mounted-root package/initramfs transaction and physical-board
acceptance of the newly built image remain user-side checks. Historical
verification below is preserved with its actual version and scope.

## Inherited 0.1.8 verification


## Current change and evidence

Checker r2 is an application-only enhancement, with no change to kernel source,
fragment, ABI, DT override, initramfs hook or runtime/package input locks. New
fixture-based tests cover live phandle mismatch, old-image detection, corrupted
runtime, absent boot assets, missing/truncated initramfs firmware listings,
malformed provenance with private-file exclusion, incomplete expansion, failed
units, unsynchronized time, 100 Mbps links, missing commands and acceptance
summaries that retain unperformed physical tests.

The complete r2 regression run passed 91 tests without skips using the optional
OpenCL-header and clean-configuration fixtures. A subsequent focused run passed
all 13 acceptance/installer tests, including the new checker-only installer.
Installer tests stage into a temporary filesystem and verify that no kernel,
boot configuration, service or application config file is written. No new
full kernel compile, image build or physical-board result is claimed for r2.

This release corrects case-insensitive RKNPU identification in both checkers,
excludes the legacy Mali400 driver, corrects the LED pinctrl bank, explicitly
preserves the GPU platform's 200 ms power-off fallback, and installs the pinned
wireless regulatory database with an early-initramfs hook. It reports selected
boot warning counts without exposing raw kernel messages.

The new kernel ABI is 6.1.172-chatbox4-arm64. Kernel source, Valhall firmware and
Mali/RKLLM runtime versions remain pinned to the previous inputs. No Wi-Fi,
Bluetooth, camera or video subsystem is disabled to hide warnings.

A fresh source extraction and empty object directory completed real kernel
configuration, syncconfig and original Orange Pi 5 DTB compilation. Production
validators accepted the resulting configuration and DTB, including GPIO1_A2
LED mapping, 200 ms GPU delay and disabled legacy Mali400 support. This is not
a complete Image/modules compile or a boot test.

The complete native regression suite passed: 79 tests with no skips, including
the verified OpenCL-header and clean kernel-configuration fixtures. New tests
cover uppercase/mixed-case NPU names, rejection of legacy Mali400, matching LED
GPIO/pinctrl, source-fix freshness, retained warning counts without raw logs,
regdb/signature validation and actual initramfs-hook execution against relocated
firmware fixtures. No ARM64/QEMU runtime retest is claimed for this release.

See BOOT-CLEANUP.md for unresolved warnings and physical acceptance checks.
A complete WSL package transaction/initramfs build and new-kernel hardware
validation remain pending on the user's machine. No OS image is supplied.

## Previous release record: 0.1.7


## Release scope

0.1.7 adds installed/configured/enabled/runtime/tested status inspection, human
and JSON output and an explicit optional GPU computation. It extends service
evidence with UnitFileState while retaining the read-only board report,
generated-bytecode exclusion and the alignment review/future test plan.
No kernel/runtime/model selection or performance tuning changed. No new kernel
compile is claimed for this documentation/diagnostic update. Every user build
still performs a completely fresh compile.

New status behavior tests cover an unconfigured fresh image, independent service
enablement/activity/failures, full-size kernel config, disabled live device-tree
nodes, missing runtime files, unknown visibility, configuration privacy, model
advertisement without inference proof, explicit computation, probe filtering,
and CLI JSON/exit codes. Earlier board-report and overlay regressions remain.

The complete 0.1.7 native suite passed: 71 tests, no skips, including the optional
OpenCL-header and pinned-kernel clean-configuration checks. All ten new status
tests also passed under the target ARM64 Python 3.13/QEMU environment. The CLI
was run against this non-board host: it emitted valid JSON and returned failure
for absent required artifacts, without changing settings or running compute.
None of these checks establishes physical-board operation.

The complete 0.1.6 native suite passed: 61 tests, with no skips, supplying the
verified OpenCL header and pinned kernel-archive fixtures for optional checks.
This includes a clean kernel configuration check, not a new full kernel compile.
All four 0.1.6 report/overlay tests also passed using the target ARM64 Python 3.13
under QEMU with the pinned Debian root libraries. The report's command execution
failure paths are mocked there; this does not establish physical-board behavior.

## Inherited verification from 0.1.5

- A new empty object directory was configured from the pinned Rockchip source
  plus the 0.1.5 fragment, unchanged in 0.1.7. The complete kernel/modules and original Orange Pi 5
  DTB compiled successfully. ABI: 6.1.172-chatbox3-arm64.
- The resulting config has CONFIG_TRANSPARENT_HUGEPAGE=y and
  CONFIG_TRANSPARENT_HUGEPAGE_MADVISE=y; ALWAYS is not selected. No runtime
  governor/IRQ/swap/writeback/locking/storage tuning is installed.
- Production kernel packaging succeeded with the new ABI, matching DTB,
  firmware, stripped modules, depmod and provenance. Audio, RKNPU and Valhall
  configuration requirements remain checked.
- Actual target Python packages were downloaded, hash checked and extracted.
  Target Python 3.13 imported the coordinator and its standard-library
  dependencies under ARM64 QEMU using the pinned Debian root libraries.
- Coordinator HTTP tests ran both natively and using that target ARM64 Python:
  unconfigured/loading/ready states, per-backend model names, bounded slow-drip
  responses, no retry after accepted output, incremental streaming, concurrent
  request rejection, invalid inputs, CLI behavior and content-free timing logs.
- Read-only diagnostics were tested against fixture sysfs/proc files, confirming
  that values were read and never changed.
- systemd-analyze verified the coordinator unit syntax. It runs as a DynamicUser
  with no capabilities, private devices and a read-only system/home boundary.
  This is not an actual systemd boot/namespace enforcement test.
- The previous full GPU/OpenCL stack compilation and ARM64 library/package
  checks from 0.1.4 are retained. The 0.1.5 full compile also contains that stack.
  Probe tests exercise real GPU-result validation control flow using a stub;
  they do not claim physical GPU execution.
- A deliberately stale source-directory Python bytecode file was injected in a
  test project; the build entrypoint loaded fresh source instead. Its compiler
  cache-disable environment and temporary-import cleanup were verified.
- Existing configuration/password, expansion, ext4, exact dpkg guard, cleanup,
  fresh-input and Windows-entry behavioral regressions remain in the suite.
  Windows-entry tests use stub build/setup commands under Linux, not Windows.

## Remaining validation boundary

This development runtime denies mounts/chroot/ptrace. Therefore a complete WSL
mounted-root package transaction, including the new Python pre-dependency
bootstrap chain and initramfs generation, was not executed here. No complete OS
image was generated. The actual Windows launcher still needs user execution.

No physical GPU/NPU/microphone is available here. Compile/configuration/linkage
checks cannot replace on-board NVMe boot, HDMI/SSH, audio recording/playback,
OpenCL computation or RKLLM model inference. THP's performance value also needs
measurement with the chosen application. It is a capability, not a claimed win.

The coordinator's engine tests use local HTTP test servers. No real model,
transcription or speech synthesis is deployed or benchmarked in this revision.
No browser UI, GPIO button control, persistent memory or complete voice loop
is represented as implemented.

## Run tests

```bash
python3 -m unittest discover -s tests -v
```

For the native OpenCL probe tests, install host OpenCL C headers or set
CHATBOX_TEST_OPENCL_HEADERS to an extracted verified include directory.
For the clean-configuration integration test, set CHATBOX_TEST_KERNEL_ARCHIVE to
the pinned source tarball. These optional test fixtures are not reused by the
production builder: actual builds always download fresh inputs and recompile.

Board acceptance: HARDWARE-TESTS.md. Coordinator setup: COORDINATOR.md.
