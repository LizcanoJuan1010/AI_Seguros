# Tasks: Live AI Voice Call with Deepgram STT/TTS

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1400–1900 (9 new files, 7 modified, across 3 services + tests) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (foundation) → PR 2 (Python) → PR 3 (Nest) → PR 4 (frontend) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No (resolved — user chose Feature Branch Chain)
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units — Feature Branch Chain

Tracker branch: `feat/live-call-deepgram` → `main` (draft, no-merge until all 4 children are integrated — this feature has no useful "half-shipped" state, e.g. the Nest gateway is dead weight without the Python endpoint).

| Unit | Goal | PR | Branch | Base | Notes |
|------|------|----|--------|------|-------|
| 1 | Foundation: enum migration, env config, nginx fix | PR 1 | `live-call-deepgram/foundation` | `feat/live-call-deepgram` | ~60–100 lines, unblocks 2 & 3 |
| 2 | Python `/ws/voice/live` + Deepgram STT/TTS + pytest | PR 2 | `live-call-deepgram/python-voice` | `live-call-deepgram/foundation` | ~450–600 lines — watch: may need its own split (state machine vs Deepgram clients) if it runs long |
| 3 | Nest `live-call` gateway/service + Jest | PR 3 | `live-call-deepgram/nest-gateway` | `live-call-deepgram/python-voice` | ~400–550 lines — contract-only dependency on PR 2 (frozen WS protocol from design.md, not its implementation) |
| 4 | Frontend `useLiveVoiceCall` + AudioWorklet + page wiring | PR 4 | `live-call-deepgram/frontend-wiring` | `live-call-deepgram/nest-gateway` | ~400–550 lines — depends on PR 3's frame contract, not its code |
| — | Tracker (maps the chain, draft/no-merge) | PR 5 | `feat/live-call-deepgram` | `main` | Merges to `main` only after PR 1-4 are reviewed and integrated |

## Phase 1: Foundation

- [x] 1.1 Add `WEB_VOICE_CALL` to `Channel` enum in `apps/backend/prisma/schema.prisma`; run `prisma migrate dev`
- [x] 1.2 Add `DEEPGRAM_API_KEY` to `apps/ai/app/config.py` and `docker-compose.yml` (`seguria-ai` env). `.env.example` (root) left for the user — `.env*` paths are denied by this project's permission settings
- [x] 1.3 Add `ws`+`@types/ws` to `apps/backend/package.json`; add `websockets` to `apps/ai/requirements.txt`
- [x] 1.4 Fix `deploy/nginx.conf` `/api/v1/` location: add `Upgrade`/`Connection`/`proxy_http_version 1.1` headers

## Phase 2: Python Voice Endpoint (`apps/ai`)

- [x] 2.1 Create `apps/ai/app/voice_live.py`: `VoiceSession` state machine (connect→auth→open Deepgram STT→loop→cleanup)
- [x] 2.2 Deepgram STT client (`/v1/listen`): forward PCM16 frames, parse partial/final transcripts
- [x] 2.3 Deepgram TTS client (`/v1/speak`): stream reply text, relay PCM16/24kHz chunks back
- [x] 2.4 On `is_final` transcript, invoke `_run_llm`/`_run_demo` from `assistant.py` unmodified; parse SSE-string output into `(event,data)` frames
- [x] 2.5 Barge-in: cancel in-flight TTS + emit `barge_in` when a new final transcript arrives during `assistant_speaking`
- [x] 2.6 Register `/ws/voice/live` route in `apps/ai/app/main.py`

## Phase 3: NestJS Gateway (`apps/backend`)

- [ ] 3.1 Create `apps/backend/src/modules/live-call/live-call.module.ts` (imports `AiCallsModule`, `CallMessagesModule`)
- [ ] 3.2 Create `live-call.gateway.ts`: `@WebSocketGateway({path:'/api/v1/live-call'})`; reject connections without valid post-connect JWT auth frame
- [ ] 3.3 Dial outbound `ws` client to Python `/ws/voice/live`; relay binary+JSON frames both directions unmodified
- [ ] 3.4 Create `live-call.service.ts`: `AiCallsService.openSession` wiring (`phone="web:"+claims.sub`, channel `WEB_VOICE_CALL`), `CallMessagesService` writes on `transcript_final`/`turn_end`
- [ ] 3.5 Cascade-close + status mapping (COMPLETADA/ABANDONADA/FALLIDA), mirroring `mapCallStatus` in `elevenlabs.service.ts`
- [ ] 3.6 Register `LiveCallModule` in `apps/backend/src/app.module.ts`

## Phase 4: Frontend (`apps/frontend`)

- [ ] 4.1 Create `useLiveVoiceCall.ts`: WS client, auth handshake, event handlers mirroring `useAssistantChat.ts`
- [ ] 4.2 Mic capture (AudioWorklet, PCM16/16kHz) + TTS playback (PCM16/24kHz)
- [ ] 4.3 Wire `LiveAiCallPage.tsx` to the hook — replace `STEPS` mock with live transcript/orb state
- [ ] 4.4 Map `tool_result` → `CallCard[]`; wire `CallControls`/`AiVisualizerStub` to real mute/state

## Phase 5: Testing (per spec scenarios)

- [ ] 5.1 pytest: `VoiceSession` transitions, barge-in trigger/no-interrupt-on-silence, mocked Deepgram WS
- [ ] 5.2 Jest: gateway auth reject path, cascade-close status mapping (3 scenarios from spec)
- [ ] 5.3 Integration test: Nest↔Python relay against a stub Deepgram WS server
