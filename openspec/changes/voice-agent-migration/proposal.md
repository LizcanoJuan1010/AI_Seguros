# Proposal: Migrar la llamada de voz al Voice Agent de Deepgram

## Intent

El spike (`voice-agent-spike`) confirmó de punta a punta que el Voice Agent
de Deepgram (STT+LLM+TTS en una sola conexión) funciona con DeepSeek como
`think` custom y ejecuta nuestras herramientas reales vía function calling
(~1.9s a primer audio, function-calling correcto contra Postgres). La
llamada real sigue lenta porque `voice_live.py` sigue con STT/TTS/DeepSeek
por separado. Esta propuesta reemplaza esa orquestación.

## Scope

### In Scope
- Reescribir `voice_live.py`: una sola conexión a
  `wss://agent.deepgram.com/v1/agent/converse` en vez de STT+TTS+DeepSeek
  separados (Python sigue manteniéndola; Nest relaya igual que hoy).
- Las 27 herramientas de `TOOLS_SCHEMA` como `functions` del `think`,
  resueltas con la MISMA `_exec_tool` — sin duplicar lógica en Nest/TS.
- `SYSTEM_PROMPT_VOICE` pasa a ser el `think.prompt`, con `mem_ctx` igual.
- Traducir eventos nativos (`ConversationText`, `FunctionCallRequest`,
  audio) al vocabulario que ya consume el frontend — CERO cambios en
  `useLiveVoiceCall.ts` ni en el gateway de Nest.
- Persistir transcript/memoria al FINAL de la llamada, no por turno.

### Out of Scope
- `apps/frontend`/`apps/backend` (contrato de eventos al navegador igual).
- Chat web (SSE) / WhatsApp — siguen con `_run_llm`/`_run_demo`.
- Optimizar rondas de tool-calling en `_run_llm` (sigue vivo para web/WhatsApp).

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `voice-live-call`: cambia CÓMO se implementa contexto/turno/latencia de
  la llamada de voz (misma capacidad que `live-call-voice-quality`).

## Approach

`VoiceSession` mantiene auth/relay/`_barge_in`; `DeepgramSTT`+`DeepgramTTS`+
el loop `_run_llm`/`_run_demo` se reemplazan por `DeepgramVoiceAgent`: abre
la conexión única, manda `Settings` (`functions`=`TOOLS_SCHEMA` aplanado), y
traduce eventos — audio tal cual, `ConversationText`→transcript/token,
`FunctionCallRequest`→`_exec_tool`+`FunctionCallResponse`, fin de
turno→`turn_end`.

## Affected Areas

| Area | Impact | Description |
|------|--------|--------------|
| `apps/ai/app/voice_live.py` | Modified | Reemplaza STT+TTS+loop por conexión Voice Agent |
| `apps/ai/app/agent_core.py` | Modified | Helper para aplanar `TOOLS_SCHEMA` a `functions` |
| `apps/ai/tests/test_voice_live_session.py` | Modified | Tests contra la nueva clase (dobles del WS) |
| `apps/backend`, `apps/frontend` | None | Contrato de eventos al navegador igual |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Traducción de eventos incompleta rompe una feature (pagos, docs) | Med | Mapear cada evento actual a su equivalente antes de tocar código |
| Las 27 herramientas no calzan todas igual que `cotizar` (ya probada) | Med | Probar el flujo de cierre completo antes de dar por cerrado |
| Perder el control fino de barge-in ya afinado | Med | Mantener `Clear` equivalente; probar interrupciones reales |
| Cambiar arquitectura en medio de uso activo | Alto | Rama separada, no mergear sin probar un cierre real completo |

## Rollback Plan

`git revert` del commit — `voice_live.py` vuelve a la versión con
STT/TTS/DeepSeek separados (ya probada y en verde). No hay migración de
datos: `chat_history`/`memory` no cambian de esquema.

## Dependencies

- Cuenta Deepgram con Voice Agent habilitado (ya confirmado en el spike).
- `DEEPSEEK_API_KEY` real configurada (ya resuelto el bug de
  `DEEPSEEK_MODEL` deprecado en `voice-agent-spike`).

## Success Criteria

- [ ] Descubrimiento→cotización→cierre funciona de punta a punta con el Voice Agent.
- [ ] Ningún evento nuevo llega mal formado al frontend (mismo contrato de hoy).
- [ ] Barge-in sigue cortando la voz de la IA correctamente.
- [ ] Latencia turno-a-turno medida en una llamada real vs. el baseline viejo.
