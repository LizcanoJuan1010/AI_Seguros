# Design: Migrar voice_live.py al Voice Agent de Deepgram

## Technical Approach

Reemplazar `DeepgramSTT`+`DeepgramTTS`+el loop `_run_llm`/`_run_demo` de
`VoiceSession` por una única clase `DeepgramVoiceAgent` (conexión a
`wss://agent.deepgram.com/v1/agent/converse`, protocolo verificado
empíricamente en `voice-agent-spike`). `VoiceSession` conserva su rol de
auth/relay con Nest; lo que cambia es qué hay del otro lado del audio.

## Architecture Decisions

### Decision: Traducir eventos en vez de cambiar el contrato con el frontend

**Choice**: `voice_live.py` traduce los eventos nativos del Agent al mismo
vocabulario que ya usa `useLiveVoiceCall.ts` (`transcript_final`, `token`,
`tool_start`/`tool_result`, `turn_end`, `assistant_speaking_start/end`,
`barge_in`).
**Alternatives considered**: actualizar el frontend para hablar el
protocolo nativo del Agent — más simple del lado Python, pero cambia un
contrato ya probado en producción para una feature con usuarios reales.
**Rationale**: cero riesgo en `apps/frontend`/`apps/backend`; toda la
complejidad nueva queda contenida en un solo archivo.

### Decision: Herramientas via `functions` aplanadas de `TOOLS_SCHEMA`

**Choice**: `agent_core.py` gana `VOICE_AGENT_FUNCTIONS = [t["function"] for
t in TOOLS_SCHEMA]` — probado en el spike que Deepgram acepta el schema
completo (enums, objetos anidados) tal cual, SIN el campo `client_side`
(agregarlo rompe el parseo — verificado).
**Rationale**: cero duplicación de schema entre canales.

### Decision: Memoria — mem_ctx una vez, `_remember` por turno, sin `chat_history` por turno

**Choice**: `mem_ctx` (memoria larga) se resuelve UNA vez al conectar y se
prepende a `think.prompt` (`SYSTEM_PROMPT_VOICE` + mem_ctx). El Agent
mantiene el estado de la conversación mientras dura la conexión — ya NO
hace falta `_load_history`/`_append_history` por turno. `_remember` (que
extrae país/tipo/edad a memoria larga) se sigue llamando por cada
`ConversationText` de rol `user`.
**Alternatives considered**: seguir persistiendo en `chat_history` por
turno igual que hoy — se descarta: es redundante (el Agent ya lo hace) y
vuelve a introducir la latencia de Postgres por turno que motivó parte de
este trabajo.
**Rationale**: el Agent resuelve continuidad DENTRO de la llamada; nuestra
tabla solo necesita capturar lo que sobrevive ENTRE llamadas.

## Data Flow

```
Browser mic ──PCM16──▶ Nest relay ──▶ VoiceSession._client_loop
                                            │ (audio tal cual, sin cambios)
                                    DeepgramVoiceAgent (wss .../converse)
                                            │
                    ┌───────────────────────┼────────────────────────┐
                    │ ConversationText      │ FunctionCallRequest    │ audio binario
                    ▼ (role=user/assistant) ▼                        ▼
            transcript_final/token   _exec_tool (Postgres)   reenvío directo
                    │                       │ FunctionCallResponse   al navegador
                    └──────────┬────────────┘
                               ▼
                    tool_start/tool_result + turn_end → Nest → Browser
```

## Interfaces / Contracts

Mapeo de eventos (nativo del Agent → evento actual al frontend):

| Evento del Voice Agent | Evento hacia el frontend | Nota |
|---|---|---|
| `ConversationText` (role=user) | `transcript_final` | Sin equivalente de `transcript_partial` confirmado — ver Open Questions |
| `ConversationText` (role=assistant) | `token` | Llega por fragmentos, no por token individual |
| `FunctionCallRequest` | `tool_start` + ejecución local + `tool_result` | Response: `_exec_tool` con los mismos argumentos que hoy |
| `UserStartedSpeaking` (con IA hablando) | `barge_in` | A confirmar si el Agent ya corta su propio audio o hay que mandar algo |
| audio binario | audio binario | Sin cambios (mismo formato PCM) |
| fin de turno (evento a confirmar) | `turn_end`, `assistant_speaking_end` | Ver Open Questions |

## File Changes

| File | Action | Description |
|------|--------|--------------|
| `apps/ai/app/voice_live.py` | Modify | `DeepgramVoiceAgent` reemplaza `DeepgramSTT`/`DeepgramTTS`; `VoiceSession` traduce eventos |
| `apps/ai/app/agent_core.py` | Modify | `VOICE_AGENT_FUNCTIONS` (TOOLS_SCHEMA aplanado) |
| `apps/ai/tests/test_voice_live_session.py` | Modify | Dobles del WS del Agent en vez de STT/TTS separados |

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | Traducción de cada tipo de evento nativo → evento de frontend | Tabla de casos, sin red real |
| Unit | `FunctionCallRequest`→`_exec_tool`→`FunctionCallResponse` con args reales | Reusa fixtures de Postgres existentes |
| Integration | Sesión completa contra un doble del WS del Agent | Extender `test_voice_live_endpoint.py` |
| Manual | Una llamada real de cierre completo (el flujo más largo/dependiente) | No automatizable en esta sesión — requiere audio real |

## Migration / Rollout

Sin migración de datos. Rama separada; no mergear a la rama de trabajo
actual sin probar una llamada real de cierre completo (según el proposal).
Rollback = `git revert`, vuelve a la arquitectura STT/TTS separada ya
probada y en verde.

## Open Questions

- [ ] ¿El Voice Agent manda transcripts PARCIALES del usuario mientras
      sigue hablando, o solo el `ConversationText` final? No confirmado.
- [ ] ¿Qué evento exacto marca "la IA terminó de hablar este turno"
      (`AgentAudioDone` u otro)? No se observó — los intentos de extender
      la prueba (mandando audio de silencio como keepalive, requisito
      confirmado empíricamente: sin audio periódico Deepgram corta con
      `CLIENT_MESSAGE_TIMEOUT` a los ~10-12s, igual que el STT) chocaron con
      `FAILED_TO_THINK` intermitente en la key de prueba antes de llegar
      ahí — a resolver con una key de producción durante el apply.
- [ ] ¿El Agent corta su propio audio automáticamente al detectar que el
      usuario empieza a hablar, o seguimos necesitando lógica propia?
- [ ] Nuevo evento observado no documentado antes: `History` (`{"type":
      "History", "role", "content"}`) — parece un log paralelo a
      `ConversationText`; revisar si conviene usarlo para el transcript que
      se persiste al final de la llamada en vez de acumular `ConversationText`.

### Manejo de fallas del `think` (hallazgo del spike, no opcional)

`FAILED_TO_THINK` ocurrió de forma intermitente contra la MISMA
configuración que antes funcionó — un fallo real de red/cuota/latencia
llamando a DeepSeek puede pasar en producción. `DeepgramVoiceAgent` MUST
manejar este `Error` con gracia (mensaje de disculpa + reintento o cierre
limpio de la llamada), no dejar la sesión colgada ni tumbar `VoiceSession`
entera — mismo criterio de degradación graciosa que el resto del proyecto.
