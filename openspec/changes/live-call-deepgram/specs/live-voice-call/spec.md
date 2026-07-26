# Live Voice Call Specification

## Purpose

Real-time voice channel for `LiveAiCallPage.tsx`. Deepgram performs STT/TTS only. NestJS relays and persists. The existing RAG/DeepSeek agent runner (`agent_core.py`) generates all replies — unmodified.

## Requirements

### Requirement: WS Session Establishment and Post-Connect Auth

The system MUST terminate a single authenticated browser WebSocket at NestJS and MUST NOT accept credentials via query parameter.

#### Scenario: Successful handshake

- GIVEN a browser holding a valid JWT
- WHEN it opens the WS and sends a post-connect auth message with the JWT
- THEN Nest validates it, opens an outbound WS to Python `/ws/voice/live`, and marks the session active

#### Scenario: Missing or invalid auth

- GIVEN a browser opens the WS
- WHEN no valid post-connect auth message arrives within the timeout, or the JWT is invalid/expired
- THEN Nest MUST close the WS with an auth error and MUST NOT open the Python leg

### Requirement: Bidirectional Audio Relay

The system MUST relay raw PCM16/16kHz audio unmodified browser→Nest→Python→Deepgram STT, and relay Deepgram TTS audio chunks Python→Nest→browser as produced, without buffering the full reply.

#### Scenario: Mic audio reaches Deepgram STT

- GIVEN an active session
- WHEN the browser streams PCM16 frames
- THEN Nest and Python forward each frame in order to Deepgram `/v1/listen` without transformation

#### Scenario: TTS streams to the browser as generated

- GIVEN the agent has produced reply text (partial or full)
- WHEN Deepgram TTS emits audio chunks
- THEN Python and Nest relay each chunk to the browser immediately, enabling playback before the full reply completes

### Requirement: RAG Agent Reuse on Finalized Transcripts

The system MUST invoke the same agent runner used by `assistant.py` (same RAG, tools, tenant/user-keyed memory) only when Deepgram STT marks a transcript `is_final`, and MUST NOT introduce new agent or tool logic for this channel.

#### Scenario: Final transcript triggers a turn

- GIVEN Deepgram STT marks a segment `is_final`
- WHEN Python receives it
- THEN it invokes the shared `agent_core.py` runner exactly as `assistant.py` does

#### Scenario: Interim transcripts are ignored

- GIVEN Deepgram STT emits a non-final transcript
- WHEN Python receives it
- THEN it MUST NOT invoke the agent runner

### Requirement: Non-Audio Event Frames

The system MUST emit agent events (`thinking`, `tool_start`, `tool_result`, `quick_replies`, `checkout_step`, `policy`, `claim`, `underwriting`, `done`, `error`) as JSON frames on the same WebSocket, using the same names and payload shapes as the SSE contract consumed by `useAssistantChat.ts`.

#### Scenario: Tool result populates call cards

- GIVEN the agent runner emits `tool_result` (e.g. from `cotizar`)
- WHEN it reaches the browser as a JSON frame
- THEN `useLiveVoiceCall` MUST map it onto `CallCard[]` using the shape `useAssistantChat.ts` expects

#### Scenario: Error event does not kill the session

- GIVEN the agent runner emits `error`
- WHEN it reaches the browser
- THEN the frontend MUST surface it without crashing the audio session, and Nest MUST NOT close the WS solely for that frame

### Requirement: Barge-In (TTS Interrupt)

The system MUST let a new finalized user transcript interrupt in-progress TTS playback.

#### Scenario: User interrupts the agent

- GIVEN TTS audio is streaming to the browser
- WHEN Deepgram STT finalizes a new user transcript
- THEN Python MUST stop the current Deepgram TTS stream and emit an interrupt frame, and the browser MUST stop playback on receipt

#### Scenario: No interruption during silence

- GIVEN TTS audio is streaming and the user has not spoken
- WHEN no new final transcript arrives
- THEN playback MUST continue uninterrupted to completion

### Requirement: Call Status Persistence on End or Drop

The system MUST persist final call status (`COMPLETADA`, `ABANDONADA`, `FALLIDA`) via `AiCallsService`/`CallMessagesService`, using mapping criteria equivalent to `mapCallStatus` in `elevenlabs.service.ts`.

#### Scenario: Clean end after content

- GIVEN the browser sends an end-of-call signal after at least one completed turn
- WHEN Nest closes the session
- THEN it MUST persist `COMPLETADA` and all recorded turns

#### Scenario: WS drop before any content

- GIVEN either leg (browser↔Nest or Nest↔Python) drops before any turn completes
- WHEN Nest detects the drop
- THEN it MUST cascade-close the other leg and persist `ABANDONADA`

#### Scenario: WS drop after an internal error

- GIVEN a leg drops due to a relay/internal error after the session started
- WHEN Nest detects the drop
- THEN it MUST persist `FALLIDA` and log the failure reason
