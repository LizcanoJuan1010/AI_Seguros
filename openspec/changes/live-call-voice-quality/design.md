# Design: Latencia, contexto y cierre en la llamada de voz

## Technical Approach

Dos frentes independientes sobre `apps/ai/app/voice_live.py`,
`agent_core.py` y `assistant.py` (spec `voice-live-call`): (A) estado/persona
— ventana de historial robusta, saludo/hint fuera del contenido persistido,
prompt de cierre por canal; (B) transporte — TTS persistente + streaming
por oración, STT migrado a Deepgram Flux. (A) no depende de (B) y se puede
enviar primero.

## Architecture Decisions

### Decision: Ventana de historial con ancla segura ampliada

**Choice**: en `_load_history` (`agent_core.py:1092`), subir `limit` de 30 a
~120 filas y ampliar qué mensaje sirve de "ancla segura" para empezar la
ventana: hoy solo acepta el primer `role=="user"`; debe aceptar también el
primer `assistant` **sin** `tool_calls` (una respuesta de turno ya
cerrada — siempre existe una al final de cada turno, ver
`assistant.py:319`). Ambos son válidos para la API (ningún `tool` colgante).

```python
for i, m in enumerate(msgs):
    if m.get("role") == "user" or (m.get("role") == "assistant" and not m.get("tool_calls")):
        return msgs[i:]
return []
```

**Alternatives considered**: resumir mensajes viejos de herramientas (más
esfuerzo, se difiere); historial ilimitado (costo/latencia sin control).
**Rationale**: cada turno normal cierra con un `assistant` sin tool_calls —
casi elimina el caso `[]`, con un cambio de una función.

### Decision: Sacar el hint de canal del contenido persistido

**Choice**: `_run_llm` recibe un parámetro nuevo `history_content: str |
None = None` (default = `message`, no rompe al chat web). `voice_live.py`
pasa `message=prompted` (con hint) y `history_content=transcript` (crudo) —
solo lo crudo se guarda en `chat_history`.

### Decision: Prompt de cierre para el canal de voz

**Choice**: nuevo `SYSTEM_PROMPT_VOICE` en `agent_core.py` = `CAMILO_INTRO`
+ `_NUCLEO_CIERRE` + `_voice_framing()`, que absorbe las restricciones de
`_VOICE_HINT_*` (respuestas cortas, nunca leer URLs, no re-saludar si el
historial ya muestra turnos previos). `_run_llm` gana `channel: str =
"web"`; `channel=="voice"` usa `SYSTEM_PROMPT_VOICE`. Esto vuelve
innecesarios `_VOICE_HINT_FIRST/CONTINUE` y `_voice_prompted_transcript` —
se eliminan de `voice_live.py`.
**Rationale**: el modelo decide "¿ya saludé?" mirando el historial real (ya
arreglado arriba), no un contador frágil reinyectado cada turno.

### Decision: TTS persistente + streaming por oración

**Choice**: una sola `DeepgramTTS` por llamada (abierta en `VoiceSession.run()`
junto al STT), reusada en todos los turnos. `cancel()` (barge-in) manda
`Clear` pero YA NO cierra el socket; solo `_cleanup()` lo cierra. `_run_turn`
detecta límites de oración en los `token` entrantes (mismo patrón que
`_MarkerBuffer` de `assistant.py`) y llama `tts.speak(oración)` apenas cada
una cierra, en vez de esperar el texto completo.
**Alternatives considered**: mantener una conexión por turno pero
precalentarla antes (menor ganancia, sigue habiendo handshake).

### Decision: STT a Deepgram Flux detrás de env var

**Choice**: `DeepgramSTT` apunta a `wss://api.deepgram.com/v2/listen?model=
flux-general-multi&language_hint=es` cuando `DEEPGRAM_STT_MODEL` empieza con
`flux-`; si no, sigue en `v1/listen` (rollback = env var, no código).
`transcripts()` mapea `EndOfTurn`→`"utterance"`, `EagerEndOfTurn`→`"partial"`
(reemplaza `looks_like_echo` para barge-in). **Abierto**: confirmar en
`developers.deepgram.com/reference/speech-to-text/listen-flux` el evento de
transcript parcial continuo antes de implementar.

## Data Flow

```
Browser mic ─PCM16─▶ Nest relay ─▶ VoiceSession._client_loop
                                        │
                                   DeepgramSTT (Flux /v2/listen)
                                        │ EndOfTurn
                                   _stt_loop ─▶ _run_turn
                                        │
                          _load_history (ancla ampliada) + mem_ctx
                                        │
                        _run_llm(channel="voice") ─▶ SYSTEM_PROMPT_VOICE
                                        │ tokens (SSE)
                             detector de oración ─▶ tts.speak(oración)
                                        │              (TTS persistente)
                                   audio chunks ─▶ Nest relay ─▶ Browser
```
Barge-in: `_stt_loop` detecta habla mientras `assistant_speaking` → `Clear`
a la MISMA conexión TTS (ya no `Close`+reconectar).

## File Changes

| File | Action | Description |
|------|--------|--------------|
| `apps/ai/app/agent_core.py` | Modify | Ancla de historial ampliada; `SYSTEM_PROMPT_VOICE`/`_voice_framing()` |
| `apps/ai/app/assistant.py` | Modify | `_run_llm(channel, history_content)` |
| `apps/ai/app/voice_live.py` | Modify | TTS persistente+streaming por oración; `DeepgramSTT`→Flux; quita `_VOICE_HINT_*` |
| `apps/ai/app/config.py` | Modify | `DEEPGRAM_STT_MODEL` default a variante Flux |
| `apps/ai/tests/test_voice_live_session.py` | Modify | Cubre ancla ampliada, no-hint-en-historial, TTS reusado |
| `apps/ai/tests/test_voice_live_endpoint.py` | Modify | URL/params de Flux en `_deepgram_listen_url()` |

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | Ancla de historial (user / assistant sin tool_calls / vacío real) | pytest sobre `_load_history` con fixtures de filas |
| Unit | Selección de prompt por `channel` | pytest sobre `_run_llm` (mock DeepSeek) |
| Integration | Turno completo de voz sin re-saludo tras 2+ turnos | `test_voice_live_session.py` (stubs Deepgram) |
| Integration | Barge-in con TTS reusado (no se cierra el socket) | extender fixtures existentes |

## Migration / Rollout

Sin migración de datos (mismo schema `chat_history`). Flux se activa
cambiando `DEEPGRAM_STT_MODEL`; con el valor anterior el pipeline sigue
igual. Desplegar (A) primero (bajo riesgo), validar en llamadas reales, y
recién después activar Flux con la env var en un subset/tenant de prueba.

## Open Questions

- [ ] Confirmar en la doc de Flux el evento de transcript parcial continuo
      (no solo `EagerEndOfTurn`) para no perder el caption en vivo del frontend.
- [ ] Confirmar si el WS de `/v1/speak` (TTS, sin cambios de Flux —
      Flux es solo STT) tolera quedar idle varios segundos entre turnos
      sin cerrarse solo del lado de Deepgram.
