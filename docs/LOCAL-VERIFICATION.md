# Local verification for this source release

- 105 host test cases passed, three skipped (108 discovered) due to unavailable test-specific tools/runtime conditions. These are host tests, not hardware tests.
- OpenCL checker compiled against verified target headers and a stub backend. Numeric success, no platform, CPU-only, wrong GPU, compiler failure, wrong output and NaN cases are covered.
- Vulkan diagnostic C compiled with warnings treated as errors. Shader compiled to Vulkan 1.0 SPIR-V and passed spirv-val. Missing-ICD rejection ran successfully. A software-ICD rejection case is available but skipped where no host software Vulkan ICD exists.
- The real Orange Pi DTS and recursive includes were fetched from the exact pinned kernel source. The release board overrides were applied, preprocessed and compiled by dtc. The resulting DTB passed board/audio/NPU/Panthor, regulator and thermal-map validation. This checks the real source rather than only synthetic DT fixtures.
- Downloaded PanVK, Rusticl and firmware package SHA256 values were verified. Their actual contents were inspected for the intended ARM64 driver/ICD files and CSF firmware. Target runtime asset hashes are included in the lock.
- All shell scripts passed bash syntax checks.

Not performed here: full cross-kernel build, QEMU image assembly, NVMe flashing, real board boot, NPU model inference, physical audio, Vulkan/OpenCL hardware execution, Whisper Vulkan or MLC Rusticl execution. Those remain acceptance gates, not implied passes.
