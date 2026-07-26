# Proposal: Live AI Voice Call with Deepgram STT/TTS

## Intent

`LiveAiCallPage.tsx` is a 100%-scripted demo. This adds real voice I/O around the EXISTING RAG/DeepSeek agent — Deepgram only handles STT/TTS, no new brain. NestJS becomes the WS relay + persistence layer, as explicitly required.

## Scope

### In Scope
- Mic capture (AudioWorklet, PCM16/16kHz) + playback in `LiveAiCallPage`/`features/call/`
- `useLiveVoiceCall` hook mirroring `useAssistantChat.ts`'s event contract
- NestJS `WebSocketGateway` relaying audio+JSON browser↔Python; persists turns via `AiCallsService`/`CallMessagesService`
- FastAPI `/ws/voice/live` holding Deepgram STT/TTS streams, feeding the existing `agent_core.py` runner
- Post-connect WS auth message (not query param)
- Barge-in cancel event; WS-drop status mapping (mirrors `elevenlabs.service.ts`)

### Out of Scope
- `agent_core.py` RAG/tool logic changes
- ElevenLabs telephony pipeline (unrelated, untouched)
- Deepgram no-credentials demo mode (flagged risk, not solved here)
- `Channel` enum decision (deferred to design)

## Capabilities

> Greenfield feature — `openspec/specs/` has no existing entries yet.

### New Capabilities
- `live-voice-call`: real-time browser↔AI voice channel (STT→RAG agent→TTS) over a NestJS-relayed WebSocket, with turn persistence and barge-in.

### Modified Capabilities
None.

## Approach

NestJS terminates the single authenticated browser WS (Python is never exposed directly, per current architecture). Nest relays raw audio + JSON frames over an outbound WS it opens to Python. Python owns two outbound Deepgram connections (`/v1/listen`, `/v1/speak`) per session, feeding finalized transcripts into the SAME agent runner powering `assistant.py`.

## Affected Areas

| Area | Impact |
|------|--------|
| `apps/frontend/src/pages/LiveAiCallPage.tsx`, `features/call/` | Modified — WS-driven state, mic capture, mute |
| `apps/frontend/src/features/assistant/` | New — `useLiveVoiceCall` hook |
| `apps/backend/src/modules/` | New — WS gateway module (+`@nestjs/websockets` dep) |
| `apps/backend/src/modules/ai-calls/`, `call-messages/` | Modified — reused for live-session persistence |
| `apps/ai/app/main.py` (or new `voice_live.py`) | New — `/ws/voice/live` endpoint |
| `apps/ai/app/config.py`, `requirements.txt` | Modified — `DEEPGRAM_API_KEY`, WS client dep |
| `docker-compose.yml` | Modified — new env var on `seguria-ai` only |
| `apps/backend/prisma/schema.prisma` | Decision pending — `Channel` enum vs. metadata (design phase) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Exceeds 400-line PR review budget — 3 services touched (Nest gateway, FastAPI WS, frontend hook+audio UI) | High | `sdd-tasks` MUST forecast per-service line counts and slice into chained/stacked PRs before `sdd-apply` starts; `delivery_strategy=ask-on-risk` requires explicit confirmation |
| Accumulated pipeline latency (mic→Nest→Python→Deepgram STT→DeepSeek→Deepgram TTS→browser) | Medium | Stream TTS on partial text, mirroring existing SSE token streaming |
| No barge-in mechanism exists today | Medium | Explicit cancel event, designed in design phase |
| Double-WS lifecycle in Nest (one leg drops) | Medium | Cascade-close + status mapping, tested in verify |
| Browsers can't set `Authorization` header on WS handshake | Low | Post-connect auth message, not query param |
| No Deepgram fallback without credentials | Medium | Out of scope here; flagged for follow-up |

## Rollback Plan

All additions are additive behind the existing `LiveAiCallPage` route — no breaking changes to SSE chat, ElevenLabs telephony, or existing DB rows. Rollback = revert the feature branch/PR slice(s); if a `Channel` enum change ships, revert via a follow-up Prisma migration. No destructive data migrations are introduced.

## Dependencies

- `DEEPGRAM_API_KEY` provisioned before `sdd-apply`
- `@nestjs/websockets` (+`ws`) added to `apps/backend`; WS client dep added to `apps/ai/requirements.txt`

## Success Criteria

- [ ] Mic audio streams to Deepgram STT via the Nest→Python relay
- [ ] Agent replies stream back as TTS using the SAME RAG/tool logic as SSE chat
- [ ] `tool_result` events populate `CallCard[]` live, matching the SSE chat contract
- [ ] Barge-in interrupts TTS playback within one turn
- [ ] Call status (COMPLETADA/ABANDONADA/FALLIDA) recorded correctly on WS drop
