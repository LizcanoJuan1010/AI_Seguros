## Exploration: Llamada IA en vivo con Deepgram (STT/TTS real-time) sobre LiveAiCallPage.tsx

### Current State

`apps/frontend/src/pages/LiveAiCallPage.tsx` is 100% mock: a hardcoded `STEPS` array advances via `setTimeout`. No mic capture, no WebSocket, no backend calls.

The RAG "brain" to reuse already exists and is well-built:
- `apps/ai/app/assistant.py` exposes `POST /api/assistant/chat/stream` (SSE), with DeepSeek function calling over `agent_core.py` (cotizar, capturar_datos_cliente, emitir_poliza, evaluar_riesgo, reportar_siniestro, etc.). Emits typed events: `thinking`, `token`, `tool_start`, `tool_result`, `quick_replies`, `document`, `checkout_step`, `policy`, `claim`, `underwriting`.
- The frontend already consumes that contract in `apps/frontend/src/features/assistant/useAssistantChat.ts`. `tool_result` payloads (e.g. from "cotizar") map directly onto the `CallCard[]` shape already hardcoded in the call page.

A different, unrelated voice pipeline already exists: outbound telephone calls via **ElevenLabs Conversational AI** (`apps/ai/app/calls.py` triggers SIP/Twilio; `apps/backend/src/modules/elevenlabs/elevenlabs.service.ts` receives the post-call webhook). This is an all-in-one black-box agent (STT+LLM+TTS bundled) that never touches the browser — not reusable as a base for this feature, only useful as a reference for degrade-clean-without-credentials and post-call persistence patterns.

There is also a batch (non-streaming) TTS proxy to a local Kokoro container (`GET /api/assistant/tts`) — not real-time, not usable for this feature.

Nothing Deepgram-related exists anywhere in the repo (`grep -ril deepgram` returns zero hits). No `WebSocketGateway` exists in the NestJS backend (`@nestjs/websockets` is not a dependency). No WebSocket endpoint exists in the Python service.

Auth: JWT Bearer stored in `localStorage` (`teq_access_token`), read via `apps/frontend/src/lib/authFetch.ts`. Browsers cannot set the `Authorization` header on a WebSocket handshake, so the live-call protocol needs a different auth mechanism (query param or a post-connect auth message).

The Prisma `Channel` enum (`apps/backend/prisma/schema.prisma`) has `WEB_INTEREST`, `WHATSAPP`, `EMAIL`, `WEB_CHAT`, `VOICE_CALL` — no dedicated value for a browser-based real-time voice call distinct from the ElevenLabs telephone channel.

### Affected Areas

- `apps/frontend/src/pages/LiveAiCallPage.tsx` — replace hardcoded `STEPS` with state driven by real WS events.
- `apps/frontend/src/features/call/` (`AiVisualizerStub`, `CallControls`) — need real mic capture, audio level, real mute.
- `apps/frontend/src/features/assistant/useAssistantChat.ts` — reference pattern for the new `useLiveVoiceCall` hook (same event contract, different transport).
- `apps/backend/src/modules/` — new module with a `WebSocketGateway` (none exists today; `@nestjs/websockets` needs to be added).
- `apps/backend/src/modules/ai-calls/ai-calls.service.ts`, `apps/backend/src/modules/call-messages/` — reuse `openSession()` and turn persistence for the live session.
- `apps/ai/app/main.py` — new WebSocket endpoint (FastAPI supports it natively; none exists today).
- `apps/ai/app/config.py`, `apps/ai/requirements.txt` — new `DEEPGRAM_API_KEY` env var and a WS client dependency.
- `docker-compose.yml` — no new container needed (Deepgram is an external API), just new env vars on `seguria-ai`.
- `apps/backend/prisma/schema.prisma` — decide whether `Channel` needs a new value or `VOICE_CALL` gets reused with a `metadata.source` discriminator.

### Approaches

The real fork is not "whether to use NestJS as gateway" (explicitly required by the user) — it's **where the binary audio connection terminates**.

1. **NestJS as a real audio relay (what the user asked for)** — the browser opens ONE WebSocket to NestJS; NestJS opens an outbound WS client connection to the Python service; raw audio frames flow browser↔Nest↔Python unmodified. Python holds the outbound Deepgram STT/TTS streaming connections and runs the RAG agent.
   - Pros: matches the explicit requirement; single authenticated edge (consistent with today's architecture, where Python is never reached directly from the browser); Nest can persist turn-by-turn via `AiCallsService`/`CallMessagesService` while the call is live, not only at the end.
   - Cons: one extra latency hop per audio frame (low cost — pure byte relay); Nest must manage the lifecycle of two simultaneous WebSockets per session.
   - Effort: High.

2. **Browser connects directly to Python's WS**, Nest only issues a short-lived session ticket and receives a final summary (mirrors the existing ElevenLabs webhook pattern).
   - Pros: lower latency (one hop for audio); less relay code in Nest.
   - Cons: contradicts the explicit requirement; exposes Python directly to the browser (never happens today — all external traffic enters through Nest/nginx); live in-call persistence (for cards projected during the call) becomes harder since Nest doesn't see the session while it's active.
   - Effort: Medium.

### Recommendation

Approach 1, as explicitly requested. It also fits the existing architecture best. Concrete design on the Python side:

- New `@app.websocket("/ws/voice/live")` in `main.py` (or a new `voice_live.py` module).
- Per connection: two outbound WS connections to Deepgram — `wss://api.deepgram.com/v1/listen` (STT streaming) and `wss://api.deepgram.com/v1/speak` (TTS streaming, Aura).
- When Deepgram marks a transcript `is_final`, that text is fed into the SAME runner that already powers `assistant.py` (same RAG, same tools, same memory keyed by `tenant_id`/`user_id`) — nothing new on the "brain" side.
- The reply is streamed to Deepgram TTS; the returned audio is relayed as-is up the WS chain to the browser.
- Non-audio events (`tool_result`, `checkout_step`, `policy`, etc.) travel as JSON frames over the same socket, reusing the contract `useAssistantChat.ts` already understands — so a "cotizar" `tool_result` can feed the `CallCard[]` directly.

### Risks

- **Accumulated latency**: mic → Nest → Python → Deepgram STT → DeepSeek → Deepgram TTS → Python → Nest → browser. TTS must start streaming on partial text, not wait for the full reply (mirrors how `assistant.py` already streams tokens).
- **Barge-in**: no mechanism today to interrupt TTS playback if the user speaks while the AI is talking — needs explicit design (a cancel event that cuts the Deepgram TTS stream and browser playback).
- **Double WebSocket in Nest**: if either leg drops, the other must close in cascade and the `AiCall` must be marked `ABANDONADA`/`FALLIDA` (same criteria as `mapCallStatus` in `elevenlabs.service.ts`).
- **WS auth**: browsers cannot send an `Authorization` header on the handshake — decide between a query param (leaks into access logs, worse) or a post-connect auth message (better).
- **No demo-mode defined for Deepgram**: DeepSeek and ElevenLabs degrade cleanly without credentials (`enabled()` in `calls.py`); Deepgram has no such fallback defined yet.
- **Audio format**: the browser should send PCM 16-bit/16kHz via AudioWorklet, not `MediaRecorder` (which yields compressed WebM/Opus) — simpler for the relay and Deepgram's native expectation.

### Ready for Proposal

Yes. Scope spans 3 services — worth going through `/sdd-new` (proposal → spec → design → tasks) before writing code, especially to pin down the WS protocol contract (message framing, event names) and the barge-in strategy, which are real design decisions, not mechanical implementation.
