# Design: Live AI Voice Call with Deepgram STT/TTS

## Technical Approach

Browser opens ONE authenticated WS to NestJS (`/api/v1/live-call`, global prefix applies to the gateway path explicitly since `setGlobalPrefix` does not cover WS gateways). Nest validates a post-connect auth frame, then dials an outbound WS to Python (`ws://seguria-ai:8085/ws/voice/live`) and relays audio (binary) + control/events (JSON text) byte-for-byte in both directions. Python owns two outbound Deepgram legs (`/v1/listen` STT, `/v1/speak` TTS) per session and feeds finalized transcripts into the **existing** `_run_llm`/`_run_demo` generators already used by `assistant.py`'s SSE endpoint — imported as-is, not duplicated or refactored. Non-audio events reuse the SSE vocabulary (`thinking`, `token`, `tool_start`, `tool_result`, `quick_replies`, `document`, `checkout_step`, `policy`, `claim`, `underwriting`, `payment_link`) wrapped in `{type, data}` JSON envelopes, plus new voice events.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Channel enum | Add `Channel.WEB_VOICE_CALL` (`@map("web_voice_call")`) via Prisma migration | Reuse `VOICE_CALL` + `metadata.source` discriminator | Codebase precedent: `WEB_CHAT` vs `WHATSAPP` are already separate enum values for similar "text" mediums, not metadata-discriminated. A JSON discriminator can't be filtered/indexed as cleanly as `AiCallsService.findAll({channel})` already does. Migration is a 2-line diff (enum entry + `ALTER TYPE ... ADD VALUE`), negligible against the 400-line budget. |
| Barge-in detection | Server-side (Python): triggered when a Deepgram STT interim/final transcript arrives while `assistant_speaking=true` | Client-side VAD on mic amplitude, sent as a `barge_in` frame from browser | Mic audio streams to Deepgram STT continuously (full duplex, never paused during TTS) — Deepgram already computes speech activity for free. Client VAD would duplicate that signal with worse accuracy (background noise) and add client complexity, contradicting "Python owns the state machine." `barge_in` becomes a **server→client** event only. |
| Reuse of agent runner | Python `voice_live.py` imports `_run_llm`/`_run_demo` from `assistant.py` unchanged, parses their SSE-string output back into `(event, data)` | Refactor `assistant.py`/`agent_core.py` into a transport-agnostic generator | Zero blast radius on the production SSE chat path (untouched file = untouched risk). Proposal explicitly scopes `agent_core.py` changes out. |
| Outbound WS client in Nest | Raw `ws` npm package (`WebSocket` client mode) for the Nest→Python leg | `@nestjs/websockets` only | `@nestjs/websockets` provides a **server** adapter, not a client — it cannot dial out to Python. `ws` is already a transitive dep of `@nestjs/platform-ws`; add directly. |
| Session identity for `openSession()` | Synthetic `phone = "web:" + claims.sub` (mirrors `assistant.py`'s `user_id = phone or f"web:{session_id}"` pattern for anonymous web sessions) | Add a `customerId`/phone field to the JWT or a new Customer-lookup path | `LiveAiCallPage` is an internal dashboard demo (JWT has no `phone` claim), not a real customer call. Reuses `AiCallsService.openSession` unmodified. |
| TTS audio format | Request Deepgram `/v1/speak` with `encoding=linear16&sample_rate=24000` (raw PCM, no container) | mp3/opus container | Symmetric with mic PCM16/16kHz uplink — browser plays via AudioWorklet without a decoder. **Verify exact query params against current Deepgram docs during `sdd-apply`** (see Open Questions). |
| Nest turn persistence hook | Nest inspects (peeks, doesn't just blind-relay) two JSON event types: `transcript_final` → `CallMessagesService.create({speaker: CLIENTE})`, new `turn_end` → `create({speaker: IA})` | Python calls Nest's REST API directly (like `backend_client.log_turn`) | Keeps the "Nest persists, Python doesn't touch Postgres for calls" boundary from the proposal; avoids a second HTTP round-trip mid-call. |

## WS Message Protocol

**Binary frames** (both directions, no envelope — direction disambiguates purpose): browser→Nest→Python = mic PCM16LE/16kHz mono; Python→Nest→browser = Deepgram TTS PCM16/24kHz mono, relayed as received (no rebuffering).

**JSON text frames** — envelope `{"type": "<name>", "data": {...}}`:

| type | Direction | Purpose |
|---|---|---|
| `auth` | C→S (first frame) | `{token}` JWT, forwarded by Nest to Python as-is |
| `auth_ok` / `auth_error` | S→C | Handshake result |
| `mute` / `unmute` | C→S | Pause/resume STT forwarding without closing |
| `end_call` | C→S | Graceful hangup |
| `transcript_partial` / `transcript_final` | S→C | Deepgram STT captions; `transcript_final` also triggers the agent turn and Nest's `CallMessage` (CLIENTE) write |
| `thinking`,`token`,`tool_start`,`tool_result`,`quick_replies`,`document`,`checkout_step`,`policy`,`claim`,`underwriting`,`payment_link` | S→C | Reused verbatim from the SSE vocabulary |
| `turn_end` | S→C | `{reply_text}` — end of one agent turn; triggers Nest's `CallMessage` (IA) write and starts TTS |
| `assistant_speaking_start` / `assistant_speaking_end` | S→C | Wraps a TTS audio burst (drives orb state) |
| `barge_in` | S→C | Cancels in-flight TTS; client must locally flush its playback queue immediately |
| `call_status` | S→C | Final `COMPLETADA/ABANDONADA/FALLIDA` before close |

## Sequence Diagram — Happy Path

```
Browser          Nest gateway         Python /ws/voice/live      Deepgram STT/TTS
  |--WS connect-->|                        |                          |
  |--auth{jwt}--->|--verify JWT (JwtService)                          |
  |               |--WS connect + auth{jwt}->|--verify (auth.decode_token)
  |               |                        |--open /v1/listen------->|
  |               |<--auth_ok--------------|<--auth_ok----------------|
  |<--auth_ok-----|  (openSession WEB_VOICE_CALL, CallMessagesService ready)
  |--mic PCM16--->|--relay-------------->  |--relay-------------->    |
  |               |                        |<--interim/final transcript
  |<--transcript_partial/final-------------|  (final -> _run_llm/_run_demo)
  |               |<--transcript_final(persist CLIENTE)               |
  |<--token/tool_result/... (streamed)-----|                          |
  |               |<--turn_end(persist IA)-|--open /v1/speak, send text->|
  |<--assistant_speaking_start-------------|<--PCM audio chunks---------|
  |<--TTS audio (binary)-------------------|<--relay as-is--------------|
  |<--assistant_speaking_end---------------|  (Flushed)                  |
```

## Sequence Diagram — WS Drop / Error

```
Browser leg drops (network/close)
  -> Nest onDisconnect: close Python leg, compute status
     (graceful end_call -> COMPLETADA; >=1 turn exchanged -> ABANDONADA; 0 turns -> FALLIDA)
     -> AiCallsService.update(aiCallId, {status, endedAt})

Python leg / Deepgram drops first (crash, STT/TTS WS error)
  -> Python sends {type:"error"} best-effort, closes its socket
  -> Nest onPythonClose: send {type:"error"} to browser, close browser socket (custom close code)
     -> AiCallsService.update(aiCallId, {status: FALLIDA, endedAt})
```

## File Changes

| File | Action | Description |
|---|---|---|
| `apps/backend/prisma/schema.prisma` + new migration | Modify | Add `Channel.WEB_VOICE_CALL` |
| `apps/backend/src/modules/live-call/live-call.module.ts` | Create | Imports `AiCallsModule`, `CallMessagesModule` |
| `apps/backend/src/modules/live-call/live-call.gateway.ts` | Create | `@WebSocketGateway({path:'/api/v1/live-call'})`, dual-WS relay, auth handshake, cascade-close |
| `apps/backend/src/modules/live-call/live-call.service.ts` | Create | `openSession` wiring, `CallMessage` writes on `transcript_final`/`turn_end`, status finalization |
| `apps/backend/src/app.module.ts` | Modify | Register `LiveCallModule` |
| `apps/backend/package.json` | Modify | Add `ws`, `@types/ws` |
| `apps/ai/app/voice_live.py` | Create | `/ws/voice/live` endpoint, `VoiceSession` state machine, Deepgram STT/TTS clients |
| `apps/ai/app/main.py` | Modify | `app.include_router(voice_live_router)` |
| `apps/ai/app/config.py`, `apps/ai/requirements.txt` | Modify | `DEEPGRAM_API_KEY`, WS client dep (`websockets`) |
| `docker-compose.yml` | Modify | `DEEPGRAM_API_KEY` env on `seguria-ai` |
| `deploy/nginx.conf` | Modify | **New requirement found in design**: `location /api/v1/` needs `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; proxy_http_version 1.1;` or the WS handshake never reaches Nest. Not in proposal's affected-areas table — flagged here. |
| `apps/frontend/src/features/assistant/useLiveVoiceCall.ts` | Create | WS client hook mirroring `useAssistantChat`'s event contract |
| `apps/frontend/src/features/call/*.tsx`, `pages/LiveAiCallPage.tsx` | Modify | Mic capture (AudioWorklet), playback, real state instead of `STEPS` mock |

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit (Python) | `VoiceSession` transitions, barge-in trigger condition, SSE-frame parsing of `_run_llm`/`_run_demo` output | pytest, mocked Deepgram WS |
| Unit (Nest) | Auth handshake reject paths, cascade-close status mapping | Jest, mocked `ws` sockets |
| Integration | Nest↔Python relay with a stub Deepgram WS server | End-to-end WS test harness |
| E2E | Full flow with real Deepgram creds (manual/CI-gated) | Deferred to `sdd-verify` |

## Migration / Rollout

One additive Prisma migration (`WEB_VOICE_CALL` enum value). No data backfill. Feature is opt-in via the existing `/llamada` route; rollback = revert PR slice(s) + follow-up migration if the enum value ships and needs removal (Postgres can't drop enum values cleanly — mitigate by not shipping the enum migration until the feature is ready to go live).

## Suggested Slicing for Tasks

1. **Prisma migration** (`WEB_VOICE_CALL`) — tiny, foundational, unblocks 3 & 4.
2. **Python `/ws/voice/live`** (`voice_live.py`, config, requirements) — standalone, testable with a WS test client, no Nest/browser needed.
3. **Nest `live-call` module** (gateway + service + nginx WS proxy fix) — testable against a stub Python WS server.
4. **Frontend** (`useLiveVoiceCall`, AudioWorklet mic/playback, `LiveAiCallPage`/`features/call/*` wiring) — testable against a mock WS server; depends on slice 3's contract being frozen, not its implementation.

## Open Questions

- [ ] Exact Deepgram `/v1/listen` and `/v1/speak` query params/control-message names (`Clear`, `Flush`) must be verified against current Deepgram docs during `sdd-apply` — used here per publicly known API shape, not independently re-verified in this session.
- [ ] Endpointing/silence threshold for Deepgram STT `is_final` (affects perceived turn-taking latency) — tune during apply/verify.
