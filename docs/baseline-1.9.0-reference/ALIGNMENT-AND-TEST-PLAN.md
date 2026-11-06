# Chatbox 0.1.5 alignment review and acceptance plan

Integration note: bundled with 0.1.6. This review records the 0.1.5 baseline.
0.1.6 implements the read-only board evidence collector and generated-bytecode
exclusion; the staged hardware, engine and voice acceptance gates still apply.

Reviewed 2026-10-31 against `opi5-voice-assistant-evaluation (1).md`, revision 3, and the actual 0.1.5 source, hardware lock, coordinator, validation notes and tests.

## Verdict

The image is on track as a hardware and application foundation. It is not yet a working speech assistant. Keep the current kernel capability set; do not add speculative kernel changes or global performance tuning in response to the evaluation. The immediate blocker is end-to-end WSL image assembly and physical-board acceptance, followed by selection and packaging of actual inference and speech engines.

The document is a useful candidate architecture, not a verified specification. Its reference-project observations, benchmark estimates and tuning proposals must not be interpreted as features or defects of our current image.

## Coverage against the document

| Area | Current 0.1.5 evidence | Next requirement |
|---|---|---|
| Original Orange Pi 5, 8 GB, Ethernet, SPI + NVMe | Builder targets this board; existing SPI is untouched; prior 0.1.0 NVMe boot was confirmed | Boot the new matched kernel, not just the earlier image |
| Clean source-only Windows/WSL build | Fresh input downloads with pinned hashes, new build workspace and kernel object directory, compiler cache disabled | Complete a real PowerShell/WSL build and retain its log |
| Single prepared boot | Kernel, modules, DTB, firmware and initramfs are assembled before flashing | Validate mounted-root package installation and initramfs in WSL; no first-boot kernel compilation |
| HDMI and GPU | Vendor display/Mali configuration compiled; firmware and OpenCL-only userspace installed | HDMI output plus real GPU computation; then model-level OpenCL test |
| Onboard audio | Vendor ES8388-compatible codec driver and ALSA packages included | Verify microphone routing, gain, playback, persistence and usable sound |
| NPU | RKNPU 0.9.8 kernel and RKLLM 1.2.3 runtime pinned | Matching converted model and actual inference; a render node alone is insufficient |
| CPU/GPU/NPU choice | Local coordinator supports explicit backend profiles and optional fallbacks | Deploy tested engines; one active LLM initially |
| Streaming | Text SSE forwarding and bounded requests implemented | Streaming ASR, text-to-clause assembly, persistent TTS worker and continuous playback are absent |
| Browser and button | Project contract recorded, no implementation | Authenticated browser control and persisted physical-button enable/disable |
| OLED | Device/controller and wiring unresolved | Identify SPI versus 8080 interface, then prove header pinmux and conflicts |
| Tuning | THP madvise; read-only clock/thermal/memory diagnostics | Baseline measurements before reversible experiments |
| User data | Gateway logs timings without conversation text | Future memory controls, audio retention rules, atomic settings and backup/restore |

## Corrections and decisions

1. The document's six-thread CPU configuration, LAN-bound LLM API, Bluetooth switching and CAP_SYS_ADMIN describe the reference project. Our coordinator binds to loopback, has no capabilities and starts no model engines. It is not running that pipeline.
2. Keep NPU LLM plus CPU streaming ASR/Piper as a leading hypothesis, not a selected winner. Compare CPU Q4 and NPU w8a8 on this board with speech workloads active. Different quantization means quality must also be compared. Published numbers from other boards do not establish our TTFT, throughput or RAM.
3. Treat 1.5-2 seconds from speech end to first audio as a stretch target. First token is not first clause, synthesized PCM or audible output. More decoding before a useful clause can dominate the remaining delay. Neither the document's estimate nor our earlier 3-6 second estimate is a measurement.
4. RKLLama is a candidate, not a drop-in dependency. Its currently retrieved README lists RKLLM 1.3.1, RKNN 2.5.0 and Python 3.9-3.12; our image pins RKLLM 1.2.3 and Python 3.13. It also describes automatic frequency changes and first-use tokenizer downloads. Pin a specific compatible revision, verify its native API/ABI and dependencies, pre-stage tokenizer/template assets for offline operation, prevent automatic tuning/downloads, and test cancellation and the exact OpenAI endpoints before adoption. Do not replace the pinned runtime casually. A small wrapper around the pinned Rockchip API remains an alternative.
5. Use w8a8 as the conservative initial RK3588 model candidate for our pinned runtime. Do not turn the document's 'w8a8 only' statement into an unrestricted claim about every RKLLM release. Any alternative format requires explicit support for this SoC, converter and runtime, followed by real inference and quality tests. GGUF CPU files and RKLLM model artifacts are distinct deployment paths.
6. Keep global DDR/CPU/NPU performance policies, IRQ reassignment, irqbalance removal, real-time audio priority, zram, writeback/sysctl and NVMe tuning out of defaults. They trade power, temperature, memory and scheduling behavior for workload-dependent gains. Discover topology and policies rather than assuming CPU or policy numbers. Avoid giving the entire Python process real-time scheduling.
7. Preserve our agreed turn-taking interface and the browser's physical-button enable/disable setting. Wake word, second-press interruption and voice barge-in are separate future features. Do not add new button gestures implicitly. Hardware AEC is device-specific and must be tested with our actual playback path; a USB audio product is not automatically an effective echo canceller.
8. Keep one LLM loaded initially. A 0.5B fast path or warm GPU fallback adds routing, quality, memory and cancellation complexity. GPU offload does not eliminate shared memory-bandwidth contention. Device indices such as opencl:1 must be discovered, not copied from the Pro guide.
9. Pin speech libraries, native dependencies, model weights, tokenizers, templates and voices separately, including licenses and hashes. The current maintained Piper repository is GPL-3.0; selected voice terms require separate inspection. Moonshine's README describes MIT defaults with exceptions for legacy non-English non-streaming models. Package availability on Debian ARM64/Python 3.13 needs confirmation before choosing Python bindings.
10. Capability coverage reduces foreseeable rebuilds; it cannot guarantee that security fixes or future runtime changes will never need another kernel.

## Acceptance gates

| Gate | Required checks | Pass evidence |
|---|---|---|
| A. Fresh build | PowerShell launcher, WSL binfmt, verified fresh downloads, ARM64 package pre-dependencies, initramfs, DTB/modules/firmware ABI, partition layout, cleanup and atomic publication | Complete build log, manifest and image hash; no first-boot compilation or reused build outputs |
| B. Boot/provision | New NVMe image without SD, Ethernet DHCP, SSH, HDMI, configured timezone/hostname/password, unique machine/SSH identity, root expansion, second boot | Correct 6.1.172-chatbox3-arm64 and NVMe root; firstboot does not repeat provisioning; credentials scrubbed as intended |
| C. Hardware | Existing HARDWARE-TESTS.md checks; mic/playback, real OpenCL numerical kernel, real RKLLM prompt, GPU/NPU DMA/IOMMU logs, USB hotplug | Repeated successful workloads, correct devices/versions, no faults; repeat under restricted worker account |
| D. Engine packaging | One CPU and one NPU LLM candidate; optional GPU after baseline; ASR and Piper candidates | Reproducible artifact lock, actual inference, bounded context/output, offline reboot/load, no root/capability requirement |
| E. Voice loop | Audio capture to streaming ASR, transcript finalization, streamed LLM text, clause TTS, bounded playback queue | First audible response measured; no duplicated/missing clauses, clipped starts/ends, stale queued speech or self-transcription |
| F. Browser/peripherals | Authenticated LAN access, no exposure of model/admin ports, settings persistence, Talk control, button debounce and disable during held press, optional OLED absent | Browser Talk works with button disabled; settings survive reboot; missing peripherals do not prevent core operation |
| G. Reliability | Network unplugged after provisioning, engine crash/hang, model missing/corrupt, malformed stream, audio unplug/replug, full data/log partition, clean shutdown, restart and recovery boot | Clear bounded errors, no restart storms, no overlapping inference or leaked playback, recoverable settings and root filesystem |
| H. Sustained use | At least 100 representative turns and a 60-minute mixed workload with intended enclosure/power/cooling | No OOM, accelerator faults, persistent XRUNs or unbounded memory growth; record throttling and slow-turn latency |

Use a disposable flashed test drive for destructive failure scenarios. Do not modify the working SPI bootloader to run these tests. Keep a known-good SD recovery route; verify that the retained recovery entry is actually reachable, not merely present in a config file.

## Reproducible performance protocol

Record board/RAM, PSU, cooling, kernel/DTB/driver/runtime hashes, model hash/quantization/context/template, affinity/thread counts, governors, ambient temperature and background services. Record available RAM, process PSS, accelerator/CMA allocations where exposed, peak usage, faults and swap. Do not double-count shared pages across workers or assume every device allocation appears in RSS.

Use the same fixed prompt corpus: greetings, commands, factual questions, short stories, numerals/names and multi-turn context. Run at least 30 measured turns per shortlisted configuration, after warm-up, and report cold-start separately. Compare short and long history. Rotate test order to limit thermal bias. Report median, p95, failures and sample count, plus answer quality. Isolated engine throughput is supplementary to full voice-loop measurements.

Add monotonic events sharing a turn ID: speech-end reference, VAD endpoint, final transcript, LLM request, first nonempty generated text, first speakable clause, first PCM ready, playback start and first audible output. API first-byte time alone is insufficient. Determine audible latency through a controlled loopback/reference recording or calibrated playback timestamps and measured device buffering. Test PTT release and VAD separately so endpointing delay is not hidden. Also record gaps between spoken clauses and total answer duration.

ASR: compare Moonshine English streaming and CPU Zipformer on representative quiet/noisy/near/far speech and the intended microphone. Measure word error rate, command accuracy, streaming finalization, real-time factor, false endpoints and missed phrase endings. Test Piper low/medium voice first-audio latency, pronunciation and synthesis throughput with short clauses and longer text.

LLM: compare RKLLM 1.5B w8a8 with llama.cpp 1.5B Q4 under ASR/TTS load. Test A76-only versus runtime default without assuming four pinned threads always wins. Introduce 0.5B only if quality and actual complete-turn time justify it. GPU/MLC and hybrid NPU/CPU remain later experiments, each requiring an actual model workload beyond the OpenCL probe.

Tuning: change one variable at a time, save and restore original settings, repeat the same corpus after thermal stabilization. Start with affinity and DDR policy only after baseline acceptance. Reject gains that worsen p95, audio underruns, reliability or temperature. Define release latency targets after the first board baseline; the present stretch target is not a release promise.

If interruption is later approved, add explicit engine abort acknowledgement, queued-PCM flushing and stale-turn rejection. Closing an HTTP socket does not prove that accelerator work has stopped. Test that a replacement turn cannot overlap an uncancelled previous request.

## Validation performed for this review

Re-ran the current source regression suite: 56 tests ran successfully, with two optional checks skipped because this invocation did not supply OpenCL headers and the kernel-archive integration fixture. Earlier release validation records a full kernel/modules/DTB compile and ARM64 coordinator tests. This review did not repeat a kernel build or generate an OS image.

Full mounted-root image assembly, real Windows execution, physical accelerator/audio operation and complete speech latency remain unverified. HTTP mock-engine tests and compiled drivers cannot establish those results.

## Implementation order

1. Complete gates A-C with the unchanged 0.1.5 source and save board diagnostics.
2. Pin compatible inference wrappers and speech/model assets; benchmark real NPU and CPU paths before selecting the default.
3. Implement the basic turn-taking voice worker and stage-level timings, then authenticated browser controls and the agreed optional button behavior.
4. Add bounded queues, history/token limits, settings persistence, privacy controls and worker recovery tests before daily-use release.
5. Identify and integrate the OLED without pin conflicts. Add optional memory/timers, wake word or interruption only as separate scoped features.
6. Optimize from measurements. Maintain a known-good rollback set and a repeatable acceptance corpus for later package/runtime/kernel updates.

## Primary references checked

- Pinned Rockchip runtime/source: https://github.com/airockchip/rknn-llm/tree/f7df8e5de9b40dc7aaa66194cf14d4895aaf159a
- RKLLama current compatibility/behavior documentation: https://github.com/NotPunchnox/rkllama
- Moonshine streaming and license documentation: https://github.com/moonshine-ai/moonshine
- Maintained Piper engine and license: https://github.com/OHF-Voice/piper1-gpl

These moving repositories are research references, not newly approved build inputs. Their exact revisions and dependency locks must be selected during implementation.
