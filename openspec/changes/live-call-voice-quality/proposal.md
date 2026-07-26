# Proposal: Corregir latencia, contexto y cierre de venta en la llamada de voz

## Intent

La llamada en vivo (`/ws/voice/live`) se siente lenta, pierde contexto,
repite el saludo, y no cierra la venta como WhatsApp. Causa raíz verificada
en código: la ventana de historial (30 filas, recortada al primer `user`)
puede devolver `[]` en turnos con muchas tool-calls, y la voz reusa el
prompt "Sofía" (informativo) en vez de "Camilo" (el que cierra).

## Scope

### In Scope
- Reparar `_load_history`/`_append_history`: nunca degradar a contexto
  vacío en turnos con muchas tool-calls.
- Sacar el hint anti-re-saludo del contenido persistido como usuario.
- Prompt de sistema de cierre para voz (variante Camilo), no Sofía.
- TTS persistente entre turnos + síntesis por oración (no esperar el turno completo).
- Migrar STT de `nova-3`/`v1/listen` a **Flux** (`v2/listen`,
  `flux-general-multi`+`language_hint=es`): turno semántico
  `EndOfTurn`/`EagerEndOfTurn` (<400ms) en vez de silencio+eco casero.

### Out of Scope
- Latencia de DeepSeek (`MAX_TOOL_ROUNDS`).
- Chat web/WhatsApp de texto (Sofía/Camilo siguen igual).
- Schema Postgres, servicios Docker, env vars (fuera de alcance).

## Capabilities

### New Capabilities
- `voice-live-call`: contexto, turno, persona de cierre y latencia de la
  llamada en vivo — sin spec previo.

### Modified Capabilities
- None.

## Approach

Dos frentes: (1) historial/persona, no dependen del proveedor, van primero;
(2) STT a Flux, reescribe `DeepgramSTT`/`_stt_loop`, reemplaza el barge-in
casero. TTS persistente + streaming por oración es el fix de mayor impacto.

## Affected Areas

| Area | Impact | Description |
|------|--------|--------------|
| `apps/ai/app/agent_core.py` | Modified | Ventana de historial robusta |
| `apps/ai/app/voice_live.py` | Modified | STT→Flux, TTS persistente, hint fuera del historial |
| `apps/ai/app/assistant.py` | Modified | Prompt por canal en `_run_llm` |
| `apps/ai/app/config.py` | Modified | Env vars de Flux |
| `apps/ai/tests/test_voice_live_session.py` | Modified | Cobertura de turno/historial |
| `apps/backend`, `apps/frontend` | None | Revisados en la exploración: el relay WS es pass-through, sin cambios |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Flux rompe barge-in (nuevo contrato de eventos) | Med | Probar interrupciones reales; flag por env var |
| TTS persistente no corta limpio en barge-in | Med | `Clear`, no `Close`, en cancel() |
| Prompt de cierre choca con restricciones de voz | Low | Fusionar, no swap ciego |

## Rollback Plan

Cada pieza es aislada — `git revert` del commit. Flux queda detrás de una
env var: volver a `nova-3` es config, no código.

## Dependencies

- Cuenta Deepgram con Flux habilitado.

## Success Criteria

- [ ] Llamada con cierre completo no repite saludo en ningún turno.
- [ ] La voz ofrece cerrar la venta, sin derivar a WhatsApp por defecto.
- [ ] Baja medible en tiempo fin-de-turno → primer byte de audio.
- [ ] `test_voice_live_session.py` cubre el nuevo camino y pasa en CI.
