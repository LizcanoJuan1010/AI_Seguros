# Tasks: Latencia, contexto y cierre en la llamada de voz

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~450-500 (agent_core ~70, assistant ~25, voice_live ~180, config ~10, tests ~170) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (estado/persona) → PR 2 (transporte TTS/STT) |
| Delivery strategy | ask-on-risk (resuelto por el usuario antes de este apply) |
| Chain strategy | stacked-to-main (confirmado por el usuario) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Historial robusto + sin re-saludo + prompt de cierre por canal | PR 1 | Independiente de Deepgram; baja el riesgo ya solo con esto |
| 2 | TTS persistente+streaming por oración + STT a Flux | PR 2 | Depende de PR 1 (usa `channel`); mayor riesgo (nuevo contrato de eventos) |

## Phase 1: Historial robusto (`agent_core.py`)

- [x] 1.1 RED: `apps/ai/tests/test_agent_core_history.py` (nuevo) — >30 filas tool/assistant sin `user` reciente espera historial no vacío
- [x] 1.2 GREEN: `_load_history` (`agent_core.py:1092`) sube `limit` a 120, acepta ancla `user` O `assistant` sin `tool_calls`
- [x] 1.3 REFACTOR: actualizar comentario; `_append_history` sin cambios

## Phase 2: Hint fuera del historial + prompt por canal

- [x] 2.1 RED: `apps/ai/tests/test_assistant.py` (nuevo) — `_history_user_message`/`_select_system_prompt` no existen aún
- [x] 2.2 GREEN: `_history_user_message(message, history_content)` pura en `assistant.py`, con 2 tests (con y sin override)
- [x] 2.3 RED/GREEN: `_select_system_prompt(role, channel)` pura en `assistant.py`, 3 tests (gerente ignora canal, voz→cierre, web→Sofía)
- [x] 2.4 GREEN: `SYSTEM_PROMPT_VOICE_DEFAULT`/`SYSTEM_PROMPT_VOICE` en `agent_core.py` (Camilo + `_CAMILO_VOICE_FRAMING`, mismo patrón que WEB/WHATSAPP/GERENTE vía `_load_active_prompt`)
- [x] 2.4b (fuera del alcance original, descubierto en apply) — `_run_demo`/`_run_demo_close` tenían el MISMO bug (re-saludo + hint mezclado en `chat_history`) para cuando `DEEPSEEK_API_KEY` no está seteada; se les aplicó `history_content` + supresión de saludo con `_load_history`, con 3 tests de integración (RED/GREEN reales contra Postgres)
- [x] 2.5 `voice_live.py`: quitó `_VOICE_HINT_FIRST/CONTINUE`, `_voice_prompted_transcript`; `_run_turn` pasa `channel="voice"` sin prefijo al transcript; `_run_demo` acepta `channel` (ignorado) para compatibilidad de firma con `runner(...)`
- [ ] 2.6 Integration: 3+ turnos sin re-saludo, avanza el cierre sin derivar a WhatsApp (specs: Sin saludo repetido, Cierre autónomo)

**— límite de PR 1 —**

## Phase 3: TTS persistente + streaming por oración

- [ ] 3.1 RED: `test_voice_live_session.py` — `DeepgramTTS.connect()` se llama una vez por llamada, no por turno
- [ ] 3.2 GREEN: mover `connect()` a `VoiceSession.run()`; `cancel()` manda `Clear` sin cerrar; `_cleanup()` cierra al final
- [ ] 3.3 RED: test que el audio arranca antes de `reply_text` completo (oraciones simuladas)
- [ ] 3.4 GREEN: detector de fin de oración en `_run_turn` (patrón `_MarkerBuffer`); `tts.speak()` por oración

## Phase 4: STT a Deepgram Flux

- [ ] 4.1 Confirmar en la doc de Flux el evento de transcript parcial continuo (pregunta abierta del design)
- [ ] 4.2 RED: `test_voice_live_endpoint.py` — espera `v2/listen`+`flux-general-multi` si `DEEPGRAM_STT_MODEL` empieza con `flux-`
- [ ] 4.3 GREEN: `_deepgram_listen_url()` condicional; `transcripts()` mapea `EndOfTurn`→utterance, `EagerEndOfTurn`→partial
- [ ] 4.4 `config.py`: `DEEPGRAM_STT_MODEL` default a flux; comentario de rollback por env var
- [ ] 4.5 Integration: barge-in real con el nuevo mapeo (spec: Interrupción del usuario)

**— límite de PR 2 —**

## Phase 5: Cleanup

- [ ] 5.1 Actualizar docstrings de `voice_live.py` que aún describen el flujo `is_final`/`speech_final` como único
- [ ] 5.2 Correr `pytest apps/ai/tests/` completo y confirmar verde
