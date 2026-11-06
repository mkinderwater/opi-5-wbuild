# Local model coordinator

The image enables chatbox-app.service on 127.0.0.1:8088. It is a stateless text
API with an included chatbox-api CLI, not a browser UI or a complete voice assistant. No engines/models are
started or downloaded. It uses only pinned Debian Python and its standard
library, without pip dependencies, Conda or an application database.

## Initial state

```bash
systemctl status chatbox-app --no-pager
chatbox-api health
chatbox-api ready
chatbox-metrics
```

/health reports process liveness. /ready returns HTTP 503 and unconfigured until
a backend is selected. This is expected, not a boot failure. Readiness means
that /v1/models on the configured engine advertises the exact selected model;
it is not proof of hardware inference or completed model initialization if the
engine itself lists models before loading them.

/diagnostics and chatbox-metrics report CPU/devfreq clocks/governors, thermal
sensors, memory/swap and THP policy. They make no writes to system settings.

## Configure a deployed backend

As root, edit /etc/chatbox/app.json. URLs must be numeric loopback HTTP endpoints
ending in /v1. DNS hostnames, remote addresses, credentials and redirect targets
are not accepted. Each backend has its own explicit model identifier.

Example after deploying a compatible llama.cpp server yourself:

```json
{
  "backend": "cpu",
  "backends": {
    "cpu": {
      "base_url": "http://127.0.0.1:8082/v1",
      "model": "qwen2.5-1.5b-instruct"
    }
  },
  "fallbacks": [],
  "timeout_seconds": 20,
  "max_tokens": 128
}
```

The model string must match that engine's actual /v1/models output. No model
name or endpoint is assumed valid merely because it appears in this example.
Restart after edits:

```bash
systemctl restart chatbox-app
chatbox-api ready
chatbox-api chat 'Hello' --stream
```

For an RKLLM or MLC wrapper, add another profile with its own URL and model.
Selecting it changes the coordinator's target, not installed engine services.
Keep one active LLM initially. The tool never starts several models to warm
fallbacks. A fresh image's only model-related daemon is this lightweight gateway.

## Boundaries and failure behavior

- Binds only to 127.0.0.1. There is no public listener or settings-write API.
- Runs as a systemd DynamicUser with no capabilities, private devices and a
  read-only system/home boundary. Compute engines need their own restricted
  services and render/audio permissions when they are implemented.
- One inference at a time. Concurrent requests receive HTTP 429 busy.
- Total upstream turn budget defaults to 20 seconds and is capped at 60.
  A wall-clock watchdog closes sockets even for slow-drip responses.
- Fallbacks are opt-in profile names. Every attempt uses its own model identifier
  and shares the same deadline. After an engine accepts an HTTP 200 response,
  there is no silent retry on another model following malformed or partial output.
  Closing an HTTP connection does not guarantee the engine cancels its own work.
- Up to 32 text messages and a 64 KiB input body; output capped at 1 MiB and the
  configured generation limit is at most 512 tokens. No tools or arbitrary shell
  commands are executed.
- Streaming SSE is forwarded as it arrives. The OpenAI-style [DONE] marker
  terminates a successful stream; EOF without it produces an error event. This is not sentence-by-sentence
  TTS. With non-streaming backends, the whole validated response is returned.
- History is supplied by the caller, bounded by the API. There is no persistent
  memory or implicit cross-request history yet.

Invalid requests return 400, missing/unready backends 503, malformed accepted
replies 502 and exhausted pre-response deadlines 504. A stream already begun
cannot change its HTTP status; it ends with an error event if upstream fails.

## Timings and privacy

```bash
journalctl -u chatbox-app -f
```

JSON records include a request ID, backend alias, readiness-probe duration,
upstream header latency, first-byte latency, total time and success/error code.
Timings use a monotonic clock. First byte is not claimed to be the first token;
a streaming backend can send metadata before text. Prompt and response content
are not logged. There are no recordings or speech-transcription logs because
speech capture is not implemented in this service.

## THP and tuning

The kernel includes CONFIG_TRANSPARENT_HUGEPAGE and the MADVISE default. Verify:

```bash
cat /sys/kernel/mm/transparent_hugepage/enabled
```

Expect `always [madvise] never`. Applications that do not request huge pages
are not forced into them by this image. No separate boot tuning service changes
THP defrag, CPU/GPU/NPU/DDR governors, IRQ affinity, swap or storage policy.
Whether THP benefits a particular model/runtime still requires measurement.

## Deferred benchmarks

After hardware and real-model acceptance, compare four A76 inference threads
against the runtime's default and measure both initial-response and sustained
speed. Detect actual CPU topology before applying affinity. Measure THP with
the intended allocator, context lengths and model format; mmap versus anonymous
memory can change its usefulness. Governor experiments should be temporary and
restorable, with temperature/power/clock records. No such experiments are applied
at image boot by this release.
