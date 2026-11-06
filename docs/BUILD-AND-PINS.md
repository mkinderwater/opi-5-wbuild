# Build and input selection

Root base: the same Johang Debian Trixie ARM64 image and hash retained from 1.9.0. Windows Build.ps1 invokes Debian WSL, copies sources into a new WSL filesystem directory, prepares binfmt/QEMU and builds there. Normal operation is NVMe-only; no SD requirement is introduced.

Kernel source stays pinned to Armbian linux-rockchip 85233a85b67928000afc2e966bab86a8c414f1b4 (6.1.172). Its existing drivers/gpu/drm/panthor backport and gpu_panthor DT node are used rather than importing an independent driver patchset or moving to an unrelated mainline kernel. This minimizes changes to vendor NPU, onboard audio, VOP/HDMI, PCIe/NVMe and board support. It does not turn a backport into an upstream-current kernel, nor establish compatibility with every future Mesa version.

GPU DT ownership switches from gpu@fb000000 to gpu-panthor@fb000000. The board GPU regulator is linked to Panthor and the SoC thermal cooling-map entry is redirected to the active node. Original source clocks/OPPs are retained. Kernel config requires Panthor as a module and rejects simultaneous proprietary Valhall. NPU ABI/version checks and the baseline LED fix remain enforced. Explicit container configuration is carried forward; unrelated newer platform-module and reliability-node gates are omitted.

Mesa selection: Debian Trixie-backports ARM64 26.1.6-1~bpo13+1 packages. Actual inspected packages contain libvulkan_panfrost.so, panfrost_icd.json and rusticl.icd. The firmware package contains arm/mali/arch10.8/mali_csffw.bin. Full runtime dependency versions, architectures, Debian pool URLs and SHA256 values are recorded in inputs/hardware-lock.json. Downloads are fresh and verified before staging. Packages/dependencies are resolved at release preparation, not against moving apt repositories during image assembly. Debian archive removal causes failure, not silent version substitution.

OpenCL is enabled for panfrost in login shells; the numeric checker enables it in its own process if unspecified. Services/containers must set RUSTICL_ENABLE=panfrost explicitly where needed. Vulkan numeric checking selects only the PanVK ICD. Normal API loaders and packaged drivers are installed; application-specific extension requirements remain runtime gates. OpenCL 3.0 enumeration would not imply optional fp16 support.

Host setup adds glslang-tools to compile a small SPIR-V numeric shader. ARM64 checker executables are cross-compiled against pinned target OpenCL/Vulkan headers and loaders. Target root execution under QEMU verifies native shared-library linkage, firmware/ICDs and generated initramfs before image publication. No GPU compute is falsely attempted under QEMU. Source kernel and package hashes, generated package hashes and build metadata remain in the image provenance.

The scratch root grows by 2 GiB before package installation to accommodate Mesa/LLVM dependencies. The final first-boot NVMe expansion behavior remains unchanged. The source ZIP contains no compiled image, model, downloaded Debian package or firmware binary.

The existing API coordinator remains installed but unconfigured, as in the baseline hardware image. No prompt/history rewrite or model application is added. Vendor RKLLM runtime remains available for its original ABI; the isolated stock RKLLama evaluation can use its own pinned runtime after platform validation.

The stable Trixie Mesa 25.0 series was rejected during preparation because PanVK Vulkan 1.2 support arrived later. This release therefore pins the packaged Trixie-backports 26.1.6 stack and its complete resolved dependency closure. It does not upgrade the OS to testing/unstable.
