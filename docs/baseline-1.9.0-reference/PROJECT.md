# Chatbox project contract

## Device

Original Orange Pi 5, preferably 8 GiB, NVMe, Ethernet DHCP and appropriate
cooling/power. Normal operation uses SPI boot firmware and NVMe, without SD.
Windows with Debian WSL2 is the build environment. Keep upstream Debian and
boot components pinned; own our assembly, provisioning, application and UI.

## User experience

A simple offline desktop voice companion: short exchanges, stories, games,
basic questions, explicit saved memory and deterministic timers/commands.
The browser provides text chat, Talk, settings, volume and diagnostics. A browser
setting enables or disables the optional physical talk button. It persists.
Disabling the button must suppress its input, including a press already in
progress. Browser Talk remains usable. No button is required for first setup.

No action is assigned to a long press, double press or shutdown gesture yet.
Audio behavior for the first version is turn-taking: capture, transcribe,
generate, speak, return to ready. No simultaneous listening while speaking.

## Architecture

Use one application coordinating clear modules, with persistent workers only
where model startup cost warrants them. Keep standard Linux networking, SSH,
time and logging. Do not add a database server, container stack, service broker
or separate network process per function.

Candidate engines: whisper.cpp, llama.cpp initially, and Piper. Choose exact
versions/models after hardware measurements. RKLLM is optional and needs a
validated kernel/driver/runtime combination; Debian 6.12's presence alone does
not establish NPU support. Earlier RK3588 NPU benchmarks are not a CPU baseline.

Current shortlist: RKLLM 1.5B w8a8 versus llama.cpp 1.5B Q4 for the LLM,
Moonshine English streaming versus CPU Zipformer for ASR, and Piper low/medium
voice for TTS. These are candidates, not bundled engines. Benchmark the full
pipeline before choosing. RKLLama needs a pinned revision compatible with our
RKLLM 1.2.3 and Python 3.13, offline tokenizer assets and controlled startup.
Keep one LLM loaded initially. No implicit warm GPU fallback or 0.5B router.
See ALIGNMENT-AND-TEST-PLAN.md for architecture decisions and release gates.

The future browser service must bind locally until browser authentication and network
exposure are implemented. Do not expose an unauthenticated settings/admin API.
Application users and GPIO/audio group permissions will be added with it.
SSH is root administration in this base release; the chatbot must not run as root.

## Hardware

The original Pi 5 has a 26-pin header. SPI OLED model, resolution and controller
remain unidentified. Other Amazon audio modules also remain unidentified.
Do not assign GPIO pins or claim that an I2S amp/mic works on this header until
pinmux/routing are proven. USB microphone plus analog amplifier remains the
simple fallback. The application must tolerate an absent OLED or disabled button.

## Milestones

1. Base builder: 0.1.0 boots NVMe, provisions SSH and expands storage on the user's board. 1.9.0 builds a matched vendor kernel with audio and RKNPU 0.9.8, installs RKLLM 1.2.3 plus Mali/OpenCL support, and generates its initramfs in WSL2 before flashing. THP uses madvise; a loopback-only text coordinator adds readiness/streaming/timings. Device-side kernel installation is removed.
2. Verify the 1.9.0 WSL2 build, first-boot HDMI, onboard audio, NPU inference, readiness and recovery on the actual board before declaring the base stable.
3. Select audio hardware; test capture and playback independently. Select and
   drive the SPI OLED, then map button/optional status LED without conflicts.
4. Authenticated browser setup/status/text chat and persisted button control.
5. Add loaded inference engines and voice turn coordination. Speak completed
   sentences while generating the remainder; bound history and response length.
6. Add timers and explicitly requested memory with view/delete controls.
7. Measure latency, recognition accuracy, temperature, memory and recovery.

A 3-6 second turn delay is an estimate for an optimized configuration, not an
acceptance result. Measure from end of speech to first audible answer over
multiple prompts, both short and long history. Keep models loaded. Record median
and slow-turn latency. Prefer concise answers and reliable turn-taking.

## Reliability and privacy

Bound logs/history. Discard captured audio after transcription by default.
Keep settings and approved memories separate from temporary conversation.
Offer clean shutdown, deliberate application updates and rollback. Restart
crashed workers, but show persistent failures rather than hiding restart loops.
Support read-only diagnostics that exclude credentials, private keys and audio.

Wake words, interruptions, document search and home automation are later work.
