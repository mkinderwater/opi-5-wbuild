# Orange Pi 5 local AI: benchmarks, failures, document uploads and thermal test notes

**Report date:** November 6, 2026  
**Hardware:** original Orange Pi 5, RK3588S, 8 GB RAM  
**Cooling assumption requested for this report:** no heatsink  
**Scope:** platform bring-up, NPU chat, CPU/GPU speech experiments, scheduling, resource reporting, WebUI documents and the 0.5.0 fresh installer.

This is a community engineering report, including what failed. It separates results observed on the Pi from host tests, source changes and work still awaiting hardware acceptance. Historical benchmark captures did not establish the cooling arrangement or ambient temperature. Treating the board as having no heatsink here does not turn those older measurements into controlled bare-board thermal tests.

## What worked best in the measured workloads

The accepted voice baseline was **Qwen2.5 1.5B on the NPU, resident Whisper tiny.en on CPU, resident Piper Lessac Medium on CPU, shared CPU scheduling, and streamed speech generation overlapping ordered playback**.

CPU Piper beat the tested Vulkan-assisted Piper implementation. Moving speech engines to strict four/four CPU groups improved one component while substantially penalizing the other. The final manual voice CLI produced complete spoken replies with pauses the tester found acceptable.

The latest fresh installer, Chatbox AI 0.5.0, returns directly to the 1.5B model and adds preconfigured local document processing, corrected upload-check authentication, autostart and a 512-token answer allowance. Its host tests passed. A full fresh 0.5.0 Pi installation and reboot acceptance were not reported in the evidence available for this document.

**No temperature, watts, sustained thermal equilibrium, or no-heatsink throttling result is claimed.** Those measurements are missing, not zero.

## 1. Evidence and provenance

| Evidence class | What it establishes | What it does not establish |
| --- | --- | --- |
| User-supplied Pi terminal results | The particular run, returned timings, errors and counters | A broad performance guarantee or an unrecorded cooling setup |
| User listening acceptance | Demonstrated replies sounded complete and pauses were acceptable | Acoustic onset timing, every utterance, or factual answer accuracy |
| Earlier consolidated findings report, current version read | Recorded platform details, matched tests and known limitations through November 4 | New hardware acceptance of later source releases |
| Current 0.5.0 source and VALIDATION.md | Exact defaults, dependency pins, installer behavior and recorded host validation | Actual ARM64 deployment success, heat or sustained hardware performance |
| Linux and Open WebUI upstream documentation | Meaning of system interfaces and configuration behavior | Measurements of this board |

The main historical record is `ORANGE_PI_CHATBOX_FINDINGS_BENCHMARKS_AND_DECISIONS_2026-11-04.md`, read in its current version for this report. Later installation failures and WebUI behavior come from the subsequent project discussion. No underlying customer document is republished; document examples are anonymized as Case A and Case B.

Benchmark-directory timestamps below are retained as recorded by the Pi. Their timezone was not established, so they have not been converted.

## 2. Hardware and platform identity matter

| Component | Recorded platform |
| --- | --- |
| Board / RAM | Original Orange Pi 5 / 8 GB |
| SoC | Rockchip RK3588S |
| CPU groups observed | Cores 4-7 higher capacity; cores 0-3 lower capacity |
| GPU | Mali-G610 MC4 |
| Storage | NVMe; a prior audit reported root on `/dev/nvme0n1p2`, approximately 235 GB after expansion |
| Audio | Onboard ES8388-family microphone/headphone path |
| NPU driver / runtime | RKNPU 0.9.8 / RKLLM 1.2.3 in the recorded platform |
| GPU kernel / userspace | Panthor / Mesa PanVK and Rusticl in the GPU experiment image |
| Cooling in original timing captures | Not recorded |
| Cooling assumed in the thermal discussion here | No heatsink; airflow, enclosure and ambient remain unspecified |

Two image generations must not be conflated:

| Image | Kernel | Status relevant to this report |
| --- | --- | --- |
| Chatbox 1.9.2 | `6.1.172-chatbox6-arm64` | Earlier application-installer baseline; vendor GPU stack |
| Chatbox 2.0.1-gpu-experimental | `6.1.172-chatbox8-arm64` | Confirmed running platform in the accepted voice evidence; Panthor/PanVK/Rusticl |
| Chatbox 2.0.2-gpu-experimental | Same chatbox8 ABI | Reviewed packaging correction for certificates/unzip; no independent flashed-board acceptance asserted here |
| Chatbox AI 0.5.0 | Application package, not an OS | Fresh-installer instructions target the supported 1.9.2 baseline; the old voice benchmark is not a 0.5.0-on-1.9.2 measurement |

The confirmed 2.0.1 release metadata declared Mesa `26.1.6-1~bpo13+1`, RKNPU 0.9.8 and RKLLM 1.2.3. Metadata is not a fresh package query. Its generated validation flags remained false because those were build-time defaults; later runtime test results need to be read separately.

The recovery-kernel ABI in that metadata, `6.12.113+deb13-arm64`, was not the kernel booted in the cited capture.

## 3. What runs where

| Work | Actual engine/path used in accepted voice tests |
| --- | --- |
| Chat generation | Qwen2.5 1.5B Instruct W8A8 through RKLLM on the NPU |
| Chat HTTP integration | GatekeeperZA-derived API with project validation, explicit Qwen token input and reset/streaming integration |
| Speech recognition | Stock whisper.cpp v1.9.5, tiny.en, CPU, four threads |
| Speech synthesis | audio.cpp v0.9.3, Piper en-US Lessac Medium GGUF, CPU, four threads |
| Experimental GPU synthesis | Same Piper voice, Vulkan decoder on Mali-G610; duration components stayed on CPU |
| Web browser | Stock Open WebUI v0.12.5 in Docker |
| New document embeddings | all-MiniLM-L6-v2 on CPU; separate from the NPU chat model |
| New Office text processing | Local parsers plus the pinned spaCy language model |

The accepted path does not imply that Whisper or Piper used the NPU. Vulkan support does not mean an application uses the GPU, and successful GPU enumeration does not establish useful model acceleration.

The manual voice CLI starts speech servers as needed and stops them on exit. It waits for playback to finish before the next recording. The tested CLI is not a full-duplex assistant: no acoustic echo cancellation, wake-word loop or barge-in is claimed.

## 4. Kernel, GPU and container findings

The image builders used the Armbian `linux-rockchip` vendor tree at commit `85233a85b67928000afc2e966bab86a8c414f1b4`, kernel 6.1.172, with `rockchip_linux_defconfig` plus the checked project fragment. The application installers do not compile or replace the kernel.

The vendor source retained the working NPU, board audio, display and NVMe integration. The GPU-experimental image used the Panthor backport in that tree, with matching firmware, device tree and Mesa userspace. It was not a claim that an arbitrary mainline kernel would preserve every board feature.

Important bring-up findings:

- The earlier image lacked Docker prerequisites. The corrected kernel profile explicitly enabled overlayfs, namespaces, seccomp, cgroups/memory/pids/cpusets, BPF and the required network/NAT facilities. The live resolved kernel is checked, not just a release name.
- Proprietary Valhall/libmali and Panthor/Mesa are different stacks. One matching driver must own the GPU; old userspace mounts should not be carried into the new stack blindly.
- OpenCL and Vulkan are userspace APIs over a complete driver/firmware stack, not kernel options called CONFIG_OPENCL or CONFIG_VULKAN.
- The later audit reported successful numeric OpenCL and Vulkan checks and Docker functionality. Those computations passed; this does not qualify every extension or model.
- FP16 was reported by the Vulkan device properties used in the TTS experiment; BF16 and matrix cores were not reported. This does not establish equivalent OpenCL FP16 support.
- The later stack's Rusticl path used `RUSTICL_ENABLE=panfrost`. A shell profile does not automatically set a service/container environment.
- Device-tree validation matters: enabled NPU/IOMMU, audio/I2S/codec, display and GPU nodes, plus the matching regulators, clocks and thermal links. A compiled module alone is not board acceptance.
- The source corrected an LED pin assignment from a pin belonging to the PMIC SPI path. Small board-description mistakes can have effects outside the advertised feature.
- Some NPU, regulator/OPP, OP-TEE and SCMI boot warnings remained in the earlier audit. Successful later inference does not prove those warnings were eliminated.

The image/kernel build ran on WSL/Linux with a separate object directory and verified source inputs. Application installers reused the supported runtime. Keep these two build layers separate when reproducing failures.

## 5. Measurement definitions

All following benchmark durations are milliseconds unless marked otherwise.

- **First text:** client-observed arrival of generated text, not completion of the answer.
- **WAV ready:** synthesis/response completion including the overhead described for the specific test.
- **First player:** software playback-process launch, not an acoustic measurement of the first audible sample.
- **RTF:** synthesis elapsed time divided by generated audio duration. Below 1 means synthesis was faster than playback for that sample. It is not a speech-quality score.
- **NPU completion:** total answer time for the request. Without matched output token counts, it is not a token-normalized decoding benchmark.
- **Whole-system CPU:** all cores together equal 100% in the resource reporter. Process CPU uses one core equal to 100%, so a multithreaded engine can exceed 100%.
- **Used system RAM:** estimated as MemTotal minus MemAvailable. It is not the chat model's allocation or a sum of process RSS.

Short samples and medians are useful evidence, but they do not establish an equilibrium temperature or sustained throughput. No p95 latency claim is made where only medians were recorded.

## 6. NPU chat latency

| Capture | First-text latency | Qualification |
| --- | --- | --- |
| Historical custom backend 0.2.2, short fixtures | Approximately 240-340 ms | Historical project record |
| Historical stock RKLLama comparison | Approximately 740-820 ms | Not a matched rerun of 0.3.0 or 0.5.0 |
| Accepted typed voice run | 262.1 ms | Different prompt from microphone run |
| Accepted microphone voice run | 233.7 ms | Part of the demonstrated voice pipeline |

The custom integration kept a model resident, prepared native tokens and streamed output promptly. Wrapper/prompt/history overhead plausibly contributed to the historical difference, but individual causes were not independently isolated. It is not evidence that the native NPU itself decoded tokens three times faster.

A later supplied conversational example reported 724.1 ms first text, 2258 ms first audio after input, four speech chunks, software-reported starvation silence 0.0 s and synthesis/playback overlap true. Only 3 of 23 prior exchanges were sent in that example. Its precise model, settings and platform were not established in the supplied excerpt, so it is not used as a matched 1.5B or 0.5.0 benchmark. Software gap counters are not acoustic gap measurements.

## 7. Standalone Piper: CPU versus Vulkan

Run: `tts-runs/20261103-222700-2538`.

One excluded process-based warmup per backend, three measured trials, alternating order. Each trial started a new process and loaded the model; these are not resident-only decoder timings.

| Backend | Median WAV-ready time, including process/load | RTF |
|---|---:|---:|
| CPU | 1223.1 | 0.282 |
| Vulkan / Mali-G610 | 4082.0 | 0.940 |

CPU was about 3.34 times faster for this engine/model/sample. Both synthesis paths completed, and playback commands succeeded. The next question was whether slower GPU speech might still help by freeing CPU capacity for transcription.

## 8. Resident overlap: Whisper, Piper and NPU together

Run: `overlap-runs/20261103-233353-2885`.

Five measured rounds per setup, alternating backend order. Speech workers were resident and warmed. A fixed WAV was reused within the run; this was synthetic request overlap, not live microphone capture during speaker playback.

Fixtures:

- Transcription: a CPU-generated and converted 16 kHz PCM16 WAV saying, "What time does the library open tomorrow morning?"
- Speech text: "Hello. This is the Orange Pi speech test. The headphone output is working."
- NPU request: describe how a library helps a community in about eighty words.

| TTS backend | Stage | Whisper | TTS | NPU completion | TTS RTF |
|---|---|---:|---:|---:|---:|
| CPU | Whisper alone | 867.3 | n/a | n/a | n/a |
| CPU | TTS alone | n/a | 1058.8 | n/a | 0.244 |
| CPU | Whisper + TTS | 1435.3 | 1624.4 | n/a | 0.374 |
| CPU | NPU alone | n/a | n/a | 16788.2 | n/a |
| CPU | Whisper + TTS + NPU | 2371.3 | 2778.9 | 15710.1 | 0.640 |
| Vulkan | Whisper alone | 876.5 | n/a | n/a | n/a |
| Vulkan | TTS alone | n/a | 3150.6 | n/a | 0.726 |
| Vulkan | Whisper + TTS | 1121.6 | 3212.8 | n/a | 0.740 |
| Vulkan | NPU alone | n/a | n/a | 16944.4 | n/a |
| Vulkan | Whisper + TTS + NPU | 1615.0 | 4435.8 | 17759.3 | 1.022 |

Under combined load, GPU TTS reduced Whisper time by approximately 32%, but increased TTS time by approximately 60%. Its RTF reached 1.022, slightly slower than real time for this fixture. CPU TTS retained more continuity margin.

This supports CPU Piper as the default for the tested combination. It is not a general claim that Mali acceleration is ineffective for every TTS engine. NPU completion times above can involve different generated answer lengths; do not rank native decoding from these totals alone.

## 9. CPU placement: invalid attempts and the valid result

Three earlier runners failed to establish the requested placement: a fixed-port restart handoff failed, a live taskset mask change did not remain valid, and even startup taskset masks later included a thread allowed on cores 0-7. The native mechanism widening affinity was not established. Those aborted tests are not successful split-core measurements.

The corrected runner used temporary systemd services, cgroup v2 and AllowedCPUs. It deliberately attempted to widen its test process and verified that the kernel kept the effective assigned cpuset. Per-stage checks recorded MainPID, thread masks and cgroup membership. These limits did not reserve those CPUs exclusively against all other processes.

Valid run: `affinity-runs/20261104-064601-20513`, five rounds. Speech engines each used four compute threads and warmed before measurement. Layout order rotated and stage order reversed on alternate rounds. The NPU service retained its scheduling.

- **Shared:** speech workers could use the shared CPU pool.
- **Whisper fast:** Whisper on cores 4-7, Piper on cores 0-3.
- **TTS fast:** Piper on cores 4-7, Whisper on cores 0-3.

| Layout | Stage | Whisper | TTS | NPU completion | TTS RTF |
|---|---|---:|---:|---:|---:|
| Shared | Whisper alone | 912.3 | n/a | n/a | n/a |
| Shared | TTS alone | n/a | 973.7 | n/a | 0.224 |
| Shared | Whisper + TTS | 1384.3 | 1540.7 | n/a | 0.355 |
| Shared | NPU alone | n/a | n/a | 16780.3 | n/a |
| Shared | Whisper + TTS + NPU | 2027.1 | 2602.9 | 16115.1 | 0.599 |
| Whisper fast | Whisper alone | 880.3 | n/a | n/a | n/a |
| Whisper fast | TTS alone | n/a | 3729.9 | n/a | 0.859 |
| Whisper fast | Whisper + TTS | 860.4 | 3721.4 | n/a | 0.857 |
| Whisper fast | NPU alone | n/a | n/a | 16901.7 | n/a |
| Whisper fast | Whisper + TTS + NPU | 1503.1 | 3969.3 | 15531.7 | 0.914 |
| TTS fast | Whisper alone | 3274.9 | n/a | n/a | n/a |
| TTS fast | TTS alone | n/a | 911.3 | n/a | 0.210 |
| TTS fast | Whisper + TTS | 3344.1 | 894.6 | n/a | 0.206 |
| TTS fast | NPU alone | n/a | n/a | 16239.6 | n/a |
| TTS fast | Whisper + TTS + NPU | 3621.0 | 2059.5 | 15198.9 | 0.474 |

Under full load, Whisper-fast improved ASR time by approximately 26% but made TTS approximately 52% slower. TTS-fast improved TTS by approximately 21% but made ASR approximately 79% slower.

Shared scheduling remained the accepted balance. Different thread counts, partial splits of the fast cores and priority policies were not tested and are not ruled out.

## 10. Governor observations and the temporary performance experiment

A captured earlier snapshot showed:

| Device/policy | Governor | Recorded frequency/range |
| --- | --- | --- |
| CPU policy0, cores 0-3 | schedutil | Allowed 1.2-1.8 GHz |
| CPU policy4, cores 4-5 | schedutil | Allowed 0.408-2.304 GHz |
| CPU policy6, cores 6-7 | schedutil | Allowed 0.408-2.304 GHz |
| DMC | dmc_ondemand | 528 MHz; allowed 528-2112 MHz |
| GPU | simple_ondemand | 200 MHz; allowed 200-1000 MHz |
| NPU | rknpu_ondemand | 1000 MHz; allowed 300-1000 MHz |

These are snapshots, not proof of sustained frequency, full device utilization or an absence of throttling.

A temporary CPU-only performance-governor test gave the following results. Prompts/replies were not byte-identical and generated audio lengths differed. Treat this as exploratory evidence, not a controlled governor speedup claim.

| Keynote test metric | Earlier schedutil run | Temporary CPU performance run |
|---|---:|---:|
| Whisper transcription ms | 837.0 | 767.0 |
| AI first text ms | 230.1 | 150.1 |
| AI last text arrival ms | 22405.0 | 15077.8 |
| Client-observed decode tokens/s | 9.02 | 12.93 |
| First player after input ms | 6904 | 4779 |
| First-chunk synthesis ms | 2994.5 | 2474.3 |
| First-chunk audio seconds | 6.153 | 5.584 |
| API prompt/output/total tokens | 27 / 201 / 228 | 27 / 194 / 221 |
| Peak system RAM MiB | 4102.6 | 4212.9 |
| Peak NPU load per core % | 79 | 86 |

The reported decode rate is client-observed text-arrival timing combined with API-reported token counts. Streaming backpressure can change it. It is not independently measured native NPU decoding speed.

The tester selected CPU performance for that earlier experiment. Instructions for a persistent CPU-only service were supplied, but successful permanent-service readback was not reported. **The 0.5.0 installer does not set CPU, NPU, GPU or DMC governors.** It leaves the image's defaults intact.

Linux's performance governor requests the policy's highest allowed frequency [K1]. It does not override thermal constraints or prove a latency benefit in every workload. With no heatsink assumed, a short latency improvement is not sufficient reason to claim sustainable maximum-clock operation.

## 11. Actual spoken interaction

Accepted sentence-based voice run results:

| Run | Input | AI first text | First player launch after input boundary | Speech chunks | Synthesis overlapped playback |
|---|---|---:|---:|---:|---|
| `20261104-071901-23279` | Typed Orange Pi question | 262.1 | 7319 | 3 | True |
| `20261104-071944-23331` | Microphone question about Christmas | 233.7 | 1791 | 14 | True |

The microphone input boundary was recording stop; first-player latency includes transcription and the following AI/TTS work. The typed run bypassed Whisper. Its longer first sentence plausibly delayed speech, while the microphone example began with a short sentence. This explanation is inferred from the reply shapes, not established by a matched per-stage experiment.

The tester confirmed complete speech and acceptable pauses for those demonstrated replies. This is listening acceptance of those samples, not a factual validation of the generated content.

A later buffer-aware source revision targeted short first/refill chunks when little audio was queued and larger sentence chunks once enough audio was available. It had 34 host coordination tests, including content/order and idle refill without new tokens. Its improved Pi latency and audible gap behavior were still awaiting acceptance in the historical record. It must not inherit the earlier sentence-mode acceptance automatically.

## 12. Resource reporting and memory

Two later reported voice turns included system resource counters:

| Transcribed question | AI first text ms | First player ms after input | CPU mean/peak % | Peak system RAM MiB | NPU core 0/1/2 mean % | NPU per-core peak % | API prompt/output/total tokens |
|---|---:|---:|---|---:|---|---:|---|
| Purpose of a generous break | 221.7 | 5629 | 15.37 / 55.72 | 4006.3 | 13.42 / 13.45 / 13.57 | 75 each | 32 / 83 / 115 |
| Purpose of an NVME | 636.7 | 10916 | 18.10 / 58.50 | 4137.7 | 15.06 / 15.09 / 15.31 | 79 each | 134 / 255 / 389 |

The question labels are retained as reported transcription labels, not polished benchmark names. Whole-turn NPU averages include recording/playback intervals; they do not establish unused inference capacity during active generation.

The governor experiment reached 4102.6 and 4212.9 MiB peak estimated system RAM for its two captures. These are distinct workloads, not a memory guarantee for all 8 GB boards. Browser activity, document import, model size, prompt length and other services can change the result.

Reporting qualifications:

- Resource sampling used 250 ms intervals; short peaks could be missed.
- Whisper and Piper each reached approximately four cores of process CPU in the reported runs.
- Per-process RSS sums can double-count shared pages and do not capture every accelerator allocation.
- NPU driver load counters are board-wide windowed values, not clean per-process attribution.
- API usage can be estimated upstream if native statistics are absent. Words, characters and stream chunks were not substituted for token counts.
- Raw temperature traces were not supplied with these summarized results.
- No measured swap-free sustained 0.5.0 document-import workload is established.

A model file's size is not its loaded-RAM requirement. Linux, UI, tokenizer, KV/runtime buffers, embeddings, parser models and speech services all matter.

## 13. Heat, assuming no heatsink

### What is known and what is missing

| Thermal question | Result available |
| --- | --- |
| Heatsink for this report's operating assumption | None |
| Cooling documented for each older timing capture | Not recorded |
| Ambient temperature / airflow / enclosure | Not recorded |
| Idle or sustained loaded SoC temperature | Not supplied |
| Peak CPU/GPU/NPU-associated temperature | Not supplied |
| Thermal equilibrium time | Not measured |
| Confirmed thermal throttling | Not established |
| Power at the board or wall | Not measured |
| Thermal shutdown or heat-related crash | Not established |

No numeric temperature range is invented. An assumption about cooling cannot supply missing sensor readings.

### Practical interpretation

CPU, GPU and NPU activity can all contribute to the board's thermal load. CPU-based tokenization, HTTP handling, embeddings and speech still run when chat generation uses the NPU. Moving one task to the GPU is not proof that the SoC or board runs cooler.

The slower Vulkan TTS result does not establish higher or lower energy use: there was no power measurement. Likewise, a low whole-turn average CPU/NPU utilization does not establish low peak temperature.

Without a heatsink, short interactive successes cannot establish sustained operation at the same speed. Heat accumulation can change later frequencies and latency. The supported conclusion is that thermal qualification remains necessary, not that this board has already been shown to overheat or to run safely without cooling under every workload.

Keep the kernel's thermal controls in place. Read the actual device-tree/driver trip points rather than publishing a generic temperature threshold for this custom image. Kernel thermal zones expose current readings and policy trip points, while cooling-device state records mitigation interfaces [K2]. A CPU-labelled thermal zone is not a separate measurement of NPU electrical power. A frequency drop alone is also insufficient to identify thermal throttling; correlate load, temperature, policy and cooling state.

### Suggested no-heatsink measurement protocol

1. Record actual absence of a heatsink, board position, enclosure, airflow, ambient temperature, power supply, image, kernel and governor settings.
2. Begin at idle with all normal services in their usual state. Save the baseline.
3. Test separate stages: short NPU response; longer/repeated NPU responses; transcription; synthesis; combined speech; document import plus chat.
4. Capture temperature, CPU/devfreq frequencies, thermal cooling states, RAM/swap and per-stage latency on the same time axis.
5. Begin with short observed runs; extend only while behavior remains acceptable. Do not disable protection or treat a critical shutdown trip as a normal operating target.
6. Compare early and late latency under the same prompt/output workload. Record any cooling intervention and restart the comparison consistently.
7. Report cooldown behavior and whether a service crash, OOM event or thermal event actually appears in logs.

For a later cooling comparison, label a heatsink/fan run separately. Do not merge its results into the no-heatsink dataset.

## 14. Audio details that made the setup usable

**Capture:** `plughw:CARD=rockchipes8388,DEV=0`, stereo PCM16 at 16 kHz; channel 0 converted to mono for ASR. Main Mic enabled, capture mute off, both capture PGAs set absolutely to +18 dB with readback. Repeated starts did not add another +18 dB. No software gain was added. Enter controlled recording with a 30-second maximum.

One early Whisper-ready measurement was 206 ms. That was startup readiness, not transcription time.

**Playback:** the hardware path worked at 48 kHz, stereo PCM16. Direct Piper 22.05 kHz mono playback failed with `Unable to install hw params`. Removing an earlier buffer override did not solve it by itself.

The accepted per-process ALSA conversion configuration was:

```text
</usr/share/alsa/alsa.conf>
pcm.chatbox_tts {
    type plug
    slave {
        pcm "hw:CARD=rockchipes8388,DEV=0"
        format S16_LE
        rate 48000
        channels 2
    }
}
```

Playback selected `chatbox_tts` with an application-local ALSA_CONFIG_PATH. ALSA performed resampling and mono-to-stereo routing. The global configuration was not replaced. An idle headphone-switch readback alone was not used to reject playback that the tester could actually hear.

## 15. Building on an 8 GB Pi: failure and recovery

A TTS build was interrupted by power loss. Fresh-only work-directory refusal prevented an immediate retry; the diagnostic installer was updated to resume verified pinned source/build/model assets and reject unknown work.

A later large Vulkan shader compilation appeared stalled and another SSH session became unresponsive. A power cycle was required. Resource pressure was suspected; no supplied OOM or thermal log proved the cause. Calling it a confirmed heat failure would be inaccurate.

This recovery procedure succeeded:

```sh
docker stop chatbox-webui
systemctl stop chatbox-npu-http
cmake --build /root/chatbox-tts-test-0.1.0/work/build \
  --target audiocpp_cli --parallel 1
```

The binary linked and synthesized successfully. Recorded unused-parameter/missing-initializer warnings were nonfatal. The later resident server target was also built using the existing tree with one compile job.

The practical lesson was to use a serial native build with competing AI/UI services stopped when needed, then restore those services. The original TTS installer still defaulted to two jobs unless BUILD_JOBS=1 was supplied; a successful manual serial build did not retroactively change that default. Kernel builds ran in WSL and are a different workload.

## 16. The 3B experiment and return to 1.5B

| Model | RKLLM download size | Evidence/status |
| --- | --- | --- |
| Original Qwen2.5 1.5B W8A8 | 2,055,447,460 bytes | Accepted earlier voice/chat baseline; selected again for 0.5.0 |
| Qwen2.5 3B W8A8 trial | 3,755,461,260 bytes | Installer prepared; later user chose the simpler model again |

There is no controlled 1.5B-versus-3B answer-quality, loaded-RAM, heat or throughput comparison in the supplied captures. Returning to 1.5B is a project choice, not proof that 3B cannot run on 8 GB or that 1.5B wins every task.

The direct model-override experiment preserved the WebUI configuration but was followed immediately by a backend connection/stream error. No subsequent service log in that exchange established its cause. Startup timing was one possibility, not a confirmed diagnosis. The first suggested health check also failed because curl was absent. The corrected check used Python's standard library.

The 0.5.0 fresh build therefore defaults directly to the 1.5B model, waits for health and runs real inference during installation. A 200 health response alone is not a model-output test.

## 17. WebUI documents: real failures and limits

### Missing embeddings in offline mode

An upload failed with `No embedding model is loaded`, despite an embedding model name already being configured. A model identifier is not the downloaded model. The earlier setup enabled offline operation before provisioning all document assets. Upstream offline guidance confirms that missing cached embeddings can leave ordinary chat working while document processing fails [W1].

The revised installer downloads and verifies local MiniLM assets and the Office parser model before the first WebUI launch. Extraction and embeddings stay local in this configuration. Offline flags are not a firewall.

### Test-token authentication failure

The first automated upload check received HTTP 401 Invalid token on TXT before any JSON/Office parsing was reached. The diagnostic token omitted the account's current session_stamp, required by the pinned WebUI validator.

The corrected script reads the current stamp, supplies session claims, applies the validator before signing, uses a short-lived token and does not claim MFA verification. Tests against the actual validator reject the old id-only claims and accept the corrected claims with simulated account storage. It refuses MFA-required diagnostic sessions rather than bypassing that requirement. The accompanying CORS warning was not the cause of the HTTP 401.

That host correction is not itself proof that all formats subsequently passed on the Pi. A full seven-format success transcript was not supplied.

### Observed document conversation

A roughly 15 KB JSON for Case A initially showed no retrieved sources and the model said it could not read the file. A later turn retrieved a source and produced a partial summary. The initial cause was not proven; unfinished processing was plausible.

An unrelated general question was then answered as though restricted to the work-order document. A later approximately 10.7 KB JSON for Case B retrieved two sources and began discussing Case A instead. This demonstrated an unreliable conversation outcome, not an isolated, verified extraction failure in Case B. Earlier files and conversation content could still affect the answer.

The old answer allowance was 256 tokens and a longer answer ended mid-date. That is consistent with output-cap truncation. The separate very short final response was not proven to have failed for the same reason; incomplete streaming/display or interruption also needed investigation.

Community lessons:

- An attached filename or file UUID is not extracted content.
- A source count does not show how much of a file reached the model.
- Retrieval finds excerpts; it does not guarantee a complete-file summary.
- One chat per case reduces cross-case contamination. A stronger prompt is not enforced source isolation.
- A generic retrieval query cannot establish exact totals over every JSON record or spreadsheet row.
- A 1.5B model can produce a fluent but wrong answer. Verify operational summaries against source records.

### Latest fresh-installer settings

| Setting | Chatbox AI 0.5.0 |
| --- | --- |
| Native model | Qwen2.5 1.5B Instruct W8A8, RKLLM 1.2.3 |
| Context / answer reserve | 4096 / 512 tokens |
| Prompt budget | 3584 tokens, including system/history/question/excerpts |
| CLI/browser model identifier | chatbox-qwen |
| Upload limits | 10 MB per file, 3 files per request |
| Chunking / retrieval | 600 characters, overlap 80, top 3 excerpts |
| Document embedding | all-MiniLM-L6-v2, local CPU, batch/concurrency 1 |
| Office parser model | en_core_web_sm 3.8.0, prepared locally |
| OCR, reranking, hybrid search | Off |
| WebUI memory limit | 2 GiB |
| Background UI generations and model tools | Disabled in this deployment |

Supported extraction paths include TXT/JSON/CSV, DOCX/XLSX/PPTX and text PDFs. Scans require OCR first; legacy DOC/XLS/PPT should be converted. Parsed spreadsheets are not an Excel calculation engine. The 512-token native cap is shared by tokenizer budget, backend, CLI and browser defaults; it can still truncate a sufficiently long reply. Leave max_tokens unset or set it to 512.

Full supplied chat history is retained or rejected when oversized; it is not silently deleted by the backend. Native KV state is reset per request for chat isolation. This does not remove old file references that the UI deliberately includes in that same conversation.

## 18. Host validation and what remains unaccepted

| Release/check | Recorded host result | Qualification |
| --- | --- | --- |
| AI 0.4.0 3B trial | 55 tests | Simulated native/systemd/Docker operations where documented |
| AI 0.4.1 upgrade path | 68 tests | Includes backend activation and rollback paths |
| AI 0.4.2 documents, before auth correction | 82 tests | Did not catch the missing session stamp before the Pi exposed it |
| Corrected AI 0.4.2 | 86 tests | Added actual-validator checks with mocked storage/MFA |
| AI 0.5.0 fresh 1.5B build | 76 tests | Removed obsolete backend-upgrade tests, retained relevant coverage, added fresh-install/512-token checks |
| Compiled native header/ctypes comparison | 76 structure/offset checks | Layout compatibility, not actual NPU execution |
| Original overlap / affinity / accepted spoken runners | 6 / 15 / 15 host tests | Historical runner revisions, not additive independent hardware tests |
| Later voice reporting/chunking revisions | 17 platform, 22 resource, 23 expanded timing, 34 buffer-policy tests | Different overlapping revisions; do not add them into one coverage total |

The smaller 0.5.0 test count is explained by removing the backend upgrade/rollback workflow from a fresh-install-only package, not by pretending all older tests apply unchanged. Relevant current authentication, cancellation, isolation, document setup and UI restoration coverage remains.

The 0.5.0 installer requires live streamed inference and generated TXT/JSON/CSV/DOCX/XLSX/PPTX/PDF upload/retrieval checks before reporting success. Those are acceptance requirements; the supplied record does not yet contain a complete fresh 0.5.0 hardware-success capture.

## 19. Boot behavior and installation scope

The NPU backend is a systemd service on `127.0.0.1:8990`. Open WebUI uses the explicitly configured host-network port 3000; do not assume that is every upstream image's default port. Docker is enabled at boot and chatbox-webui uses restart=always.

Autostart is implemented and host-tested. A separate post-change full reboot demonstration with saved-chat and new-upload checks was not reported. Speech recording/Whisper/Piper are not automatically started by the AI installer.

The 0.5.0 source package is a fresh application installer on the supported Chatbox image, not a complete OS image, generic Debian installer, speech installer or migration tool. It refuses existing services, override directories, launchers and nonempty browser data rather than overwriting them. Kernel/runtime/driver changes are outside its application install.

Example fresh application installation:

```sh
cd /root/chatbox-ai-0.5.0
python3 install.py
```

After installation, useful checks requiring no curl are:

```sh
python3 /opt/chatbox-ai-0.5.0/status.py
python3 /opt/chatbox-ai-0.5.0/probe.py
chatbox-cli --diagnostics "Say hello in one sentence."
free -h
vmstat 1
docker stats --no-stream chatbox-webui
journalctl -u chatbox-npu-http -b --no-pager -n 80
```

Use the matching older path for a historical deployment. A failed fresh-only guard is not an instruction to delete a live installation. Health/status, inference, document ingestion, answer quality and reboot persistence are separate checks.

## 20. Read-only thermal and resource capture for community reproductions

The following collector is provided as a **future measurement aid**, not a completed thermal result. It samples for about 60 seconds and writes JSON lines in the current directory. Run the workload being tested in another terminal. It does not change governors, clocks or thermal settings. Missing interfaces remain null or absent. NPU load may require root and a mounted debugfs.

```sh
python3 - <<'PY' > chatbox-telemetry.jsonl
import json
from pathlib import Path
import time


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def integer(path):
    try:
        return int(read(path))
    except (TypeError, ValueError):
        return None


def cpu_ticks():
    fields = read('/proc/stat')
    if not fields:
        return None
    values = list(map(int, fields.splitlines()[0].split()[1:9]))
    return sum(values), values[3] + values[4]


previous = None
started = time.monotonic()
for sample in range(60):
    current = cpu_ticks()
    busy = None
    if previous and current and current[0] > previous[0]:
        busy = 100 * (1 - (current[1]-previous[1])/(current[0]-previous[0]))
    previous = current
    temperatures = {}
    for zone in sorted(Path('/sys/class/thermal').glob('thermal_zone*')):
        milli = integer(zone/'temp')
        temperatures[zone.name] = {
            'type': read(zone/'type'),
            'temperature_C': milli/1000 if milli is not None else None,
            'trips_mC': {p.name: integer(p) for p in zone.glob('trip_point_*_temp')},
        }
    cpus = {p.name: {
        'governor': read(p/'scaling_governor'),
        'current_kHz': integer(p/'scaling_cur_freq'),
        'minimum_kHz': integer(p/'scaling_min_freq'),
        'maximum_kHz': integer(p/'scaling_max_freq'),
    } for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*')}
    devices = {p.name: {
        'governor': read(p/'governor'), 'current_Hz': integer(p/'cur_freq'),
    } for p in Path('/sys/class/devfreq').glob('*')}
    cooling = {p.name: {
        'type': read(p/'type'), 'state': integer(p/'cur_state'),
        'max_state': integer(p/'max_state'),
    } for p in Path('/sys/class/thermal').glob('cooling_device*')}
    memory = {}
    for line in (read('/proc/meminfo') or '').splitlines():
        key, value = line.split(':', 1)
        if key in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'):
            memory[key+'_kB'] = int(value.split()[0])
    print(json.dumps({
        'unix_time': time.time(), 'elapsed_s': time.monotonic()-started,
        'sample': sample, 'cpu_busy_percent_all_cores': busy,
        'thermal': temperatures, 'cpu_policies': cpus, 'devfreq': devices,
        'cooling': cooling, 'memory': memory,
        'rknpu_load_raw': read('/sys/kernel/debug/rknpu/load'),
    }), flush=True)
    time.sleep(1)
PY
```

Also retain `uname -r`, `/etc/chatbox/release.json`, workload/prompt and output token count, CPU placement, source/model pins, ambient/cooling notes and `journalctl -k -b`. Use MemAvailable rather than free alone when assessing memory headroom. In vmstat, disregard the first since-boot average row when checking ongoing swap-in/swap-out activity.

Sensor labels and frequencies are observations, not an automatic diagnosis of the heat source. The collector does not measure board power or audible latency. Measure wall/board power with appropriate hardware if energy efficiency is a claim you want to make.

## 21. Work still worth doing

1. Complete the full fresh 0.5.0 installation, document checks and reboot acceptance on the supported image.
2. Publish actual no-heatsink temperature/frequency/cooling-state traces with ambient and workload details.
3. Repeat governor tests with matched prompts, controlled output lengths and identical audio fixtures, including a sustained phase.
4. Compare 1.5B and 3B under the same workload if a model-size recommendation is to be generalized.
5. Validate buffer-aware speech on the Pi, including acoustic onset and audible gaps rather than software process timing alone.
6. Add explicit current-file selection and processing readiness for document questions; prompts alone cannot enforce it.
7. Build bounded, queued large-file processing before claiming 25/50 MB imports. The current upload setting remains 10 MB.
8. Separate complete-file summaries and deterministic JSON/CSV totals from ordinary excerpt retrieval.
9. Test longer sessions, cancelled work, service restarts and memory pressure with the intended concurrent services.

Flite audio samples and an OuteTTS Vulkan-first test/build were separate explorations. No attributable Pi throughput, thermal or audio-quality comparison for them is included here. They are not established replacements for the accepted Piper baseline.

## 22. Credit and reproducibility

Hands-on testing, project direction and integration work: **Matthew Kinderwater**. AI assistance was used in code iteration and report preparation. Upstream engines, models, drivers and UI remain the work of their respective authors; this project assembled, configured, tested and diagnosed them.

| Contribution | Upstream/source |
| --- | --- |
| Board and vendor support | Orange Pi / Shenzhen Xunlong and Rockchip |
| Kernel and board tree used by the builder | Linux contributors and [Armbian linux-rockchip](https://github.com/armbian/linux-rockchip) |
| Earlier Debian image foundation | [johang/sd-card-images](https://github.com/johang/sd-card-images), as attributed in the retained builder findings; preserve its original provenance/notices |
| RKLLM/RKNPU inference runtime | [Rockchip rknn-llm](https://github.com/airockchip/rknn-llm) |
| Quantized original model and API server integration base | [GatekeeperZA model](https://huggingface.co/GatekeeperZA/Qwen2.5-1.5B-Instruct-RKLLM-v1.2.3) and [RKLLM-API-Server](https://github.com/GatekeeperZA/RKLLM-API-Server) |
| Original language model | [Qwen2.5 1.5B Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct), Qwen/Alibaba team |
| GPU userspace | [Mesa](https://www.mesa3d.org/) PanVK/Rusticl and contributing driver developers |
| Speech recognition | [whisper.cpp](https://github.com/ggml-org/whisper.cpp), ggml-org and contributors; [OpenAI Whisper model authors](https://github.com/openai/whisper) |
| Speech synthesis implementation | [audio.cpp](https://github.com/0xShug0/audio.cpp), 0xShug0 and contributors; Piper/voice model authors |
| Voice conversion distribution used | [audio-cpp/audio.cpp-gguf](https://huggingface.co/audio-cpp/audio.cpp-gguf) |
| Browser and document application | [Open WebUI](https://github.com/open-webui/open-webui) and contributors |
| Embedding model | [Sentence Transformers all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) and its model authors |
| Local Office NLP model | [spaCy / Explosion model packages](https://github.com/explosion/spacy-models) |
| Transport/process/container/audio infrastructure | Python, Flask/Gunicorn, Docker, systemd, ALSA, Debian and their contributors |

Retain upstream model and software licences. A wrapper's licence or a conversion repository's metadata does not replace a model's original terms. In particular, the 3B trial has different upstream model licensing from what a reader might infer from a conversion repository label; consult its actual upstream licence before reuse.

Project-specific work includes the fresh installers, pin manifests, backend policy/native-token adapter, CLI/SSE transport, input/output orchestration, local audio setup, acceptance tools, troubleshooting and this report. It is not a new foundation model, speech engine, GPU driver or replacement UI.

### Key source pins

| Component | Pin |
| --- | --- |
| Kernel tree | `85233a85b67928000afc2e966bab86a8c414f1b4` |
| RKLLM SDK source | `f7df8e5de9b40dc7aaa66194cf14d4895aaf159a` |
| GatekeeperZA API source | `89f43f99ffe6457ed5043b3c038361951a411e60` |
| Original 1.5B RKLLM conversion revision | `c12694c6caaec26f151cbd734cb3ceced4355da3` |
| Official 1.5B tokenizer revision | `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` |
| whisper.cpp v1.9.5 | `d1be6fde11ac6e0407606b4e42fe72d34add8037` |
| audio.cpp v0.9.3 | `41c1f8ffa0d13a1b7e366e30ea5fe5ab8d169d48` |
| Piper GGUF revision | `dae47e44d47c340e5c292bc33e0137f1e9e2d835` |
| MiniLM revision | `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` |
| Tokenizers | 0.22.1, verified ARM64 wheel |
| Open WebUI | v0.12.5, pinned container digest in inputs.lock.json |
| spaCy language model | en_core_web_sm 3.8.0, verified wheel |

The chat model SHA-256 is `060ea9646fb838a389b62830b1b2096b97788675c6bc5fbd3df30adeb8c64b2e`; Piper is `c579c0010e67cb4941179405ae4587923b0372638df7b2987e758d7c97fe2e6f`; tiny.en is `921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f`. These identify different assets, not package versions. Preserve each release's inputs.lock.json and SHA256SUMS, because some older source archives were corrected in place without renaming.

### Latest delivered source archive

The local delivered `chatbox-ai-0.5.0-1.5b-webui-fresh-install.zip` snapshot is 66,389 bytes, SHA-256 `5c84325ddb24c598512bec6cbc26e9c682c1cd56f5699964cf1ff79053f53bf4`. This identifies the source ZIP reviewed here, not a compiled OS image or successful hardware installation. If the archive is rebuilt or changed, publish its new digest rather than reusing this one.

### Primary reference links

- **[K1]** [Linux CPU performance scaling](https://docs.kernel.org/admin-guide/pm/cpufreq.html): governor and policy meanings.
- **[K2]** [Linux thermal sysfs interface](https://docs.kernel.org/driver-api/thermal/sysfs-api.html): thermal zones, trip points and cooling-device interfaces.
- **[W1]** [Open WebUI offline preparation](https://docs.openwebui.com/tutorials/maintenance/offline-mode/): local model/cache preparation and offline settings.
- [Pinned audio.cpp Piper documentation](https://github.com/0xShug0/audio.cpp/blob/v0.9.3/docs/models/piper_tts.md).

For a public release, pair this report with the actual source packages and any raw reports you are authorized to share. Keep customer documents, account databases, environment secrets and diagnostic tokens out of the benchmark bundle. Missing measurements should remain explicitly missing until new captures establish them.
