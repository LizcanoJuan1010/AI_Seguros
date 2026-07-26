# Tasks: Migrar voice_live.py al Voice Agent de Deepgram

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~500-650 (voice_live.py reescritura ~300, agent_core.py ~15, tests reescritos ~250) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes, con matiz: es un reemplazo atómico (no hay "mitad de una clase WS" útil de mergear sola) |
| Suggested split | PR 1 (clase nueva + traducción de eventos, código muerto/no wireado aún) → PR 2 (cutover: reemplaza VoiceSession, borra STT/TTS viejos, tests) |
| Delivery strategy | stacked-to-main (confirmado antes en esta sesión para el cambio hermano) |
| Chain strategy | stacked-to-main |

Decision needed before apply: No (delivery strategy ya confirmada esta sesión)
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | `DeepgramVoiceAgent` + traducción de eventos, sin wireado a `VoiceSession` todavía | PR 1 | Código nuevo, no reemplaza nada — riesgo cero para la llamada actual |
| 2 | Cutover: `VoiceSession` usa la clase nueva, se borran `DeepgramSTT`/`DeepgramTTS`/loop viejo, tests reescritos | PR 2 | Depende de PR 1; acá sí cambia el comportamiento real |

## Phase 1: `DeepgramVoiceAgent` (agent_core.py + voice_live.py, sin wireado)

- [x] 1.1 `agent_core.py`: `VOICE_AGENT_FUNCTIONS = [t["function"] for t in TOOLS_SCHEMA]`
- [x] 1.2 `voice_live.py`: clase `DeepgramVoiceAgent` — `connect()` (Settings con `think.endpoint` hermano de `provider`, `functions` sin `client_side`), `inject_user_message()`, `send_audio()`, `respond_function_call()`, `close()`
- [x] 1.3 `events()`: yields `("audio", bytes)` o `(type_nativo, msg)` — sin traducir todavía, eso es Fase 2
- [x] 1.5 Unit tests (`test_voice_agent.py`, 7 casos): shape de Settings (con/sin DEEPSEEK_API_KEY, sin `client_side`), `events()` para audio/JSON, `connect()` falla explícito si Deepgram rechaza, `respond_function_call()` shape correcto
- [ ] 1.4 Manejo de `Error`/`FAILED_TO_THINK` en el LOOP de `VoiceSession` (no en la clase transporte) — pasa a Fase 2, es responsabilidad de quien orquesta el turno, no de quien lee el socket

## Phase 2: Cutover de `VoiceSession`

- [x] 2.1 `VoiceSession.run()`: conecta `DeepgramVoiceAgent`; `think.prompt` = `SYSTEM_PROMPT_VOICE` + `mem_ctx` (resuelto una vez, no por turno); sin `DEEPSEEK_API_KEY` rechaza explícito (no hay modo demo para este canal)
- [x] 2.2 `_agent_loop`/`_handle_agent_event`: traduce `ConversationText`, `UserStartedSpeaking`, `FunctionCallRequest`, `Error`, audio — reusa `_summarize_tool`/`_checkout_frames` de `assistant.py` (mismos eventos de pago/documento que el chat web)
- [x] 2.3 `_barge_in`: simplificado a avisar al frontend — sigue abierta la pregunta de cuánto maneja el Agent nativamente (ver design.md)
- [x] 2.4 `_remember` por cada `ConversationText` de rol `user`
- [x] 2.5 Borrado: `DeepgramSTT`, `DeepgramTTS`, `looks_like_echo`, `_normalize_echo_text`, `_deepgram_listen_url`, `_deepgram_speak_url`, `_TTS_FLUSH_TIMEOUT_S`, `_speak`, `_tts_reader_loop`, `_run_turn` viejo
- [x] 2.6 Reescritos `test_voice_live_session.py` (18 tests), `test_voice_live_endpoint.py` (4 tests, incluye caso sin DEEPSEEK_API_KEY), nuevo `test_voice_agent.py` (7 tests) — suite completa del proyecto en verde

## Phase 3: Validación manual (no automatizable en esta sesión)

- [ ] 3.1 Llamada real de descubrimiento→cotización→cierre completo
- [ ] 3.2 Confirmar barge-in real (interrumpir a la IA hablando)
- [ ] 3.3 Medir latencia turno-a-turno real vs. el baseline de la arquitectura vieja
- [ ] 3.4 Resolver las preguntas abiertas del design.md con datos de esta llamada real
