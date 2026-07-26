# Proposal: Spike de Deepgram Voice Agent (STT+LLM+TTS unificado)

## Intent

La llamada de voz sigue lenta en el "análisis" (turno del usuario →
respuesta) aun tras arreglar contexto y audio: cada turno cruza servicios
separados que orquestamos a mano (Python↔Deepgram STT, Python→DeepSeek,
Python↔Deepgram TTS). El **Voice Agent** de Deepgram maneja STT+LLM+TTS en
una sola conexión, con function calling — podría atacar la latencia de
raíz, pero no está confirmado con DeepSeek ni con nuestras 27 herramientas.
Este spike valida eso con datos reales antes de migrar `voice_live.py`.

## Scope

### In Scope
- Script aislado que conecta a `wss://agent.deepgram.com`, manda `Settings`
  con DeepSeek como LLM `think` (endpoint OpenAI-compatible, igual al que ya
  usamos) y UNA sola función real: `cotizar`.
- Medir latencia real turno-a-turno (fin de habla → primer byte de audio)
  contra el baseline actual.
- Confirmar si `FunctionCallRequest`/`FunctionCallResponse` es compatible
  con el schema de `cotizar` en `TOOLS_SCHEMA`.
- Reporte de resultados para decidir si se justifica migrar completo.

### Out of Scope
- Migrar `voice_live.py` de producción o las otras 26 herramientas.
- Tocar el chat web/WhatsApp.
- Cambiar `SYSTEM_PROMPT_VOICE`/persona de cierre — el spike usa un prompt
  mínimo de prueba, no el de producción.

## Capabilities

### New Capabilities
- None — spike descartable, no una capacidad a shippear. Si el resultado es
  positivo, eso es un proposal nuevo.

### Modified Capabilities
- None.

## Approach

Script standalone en `apps/ai/scripts/`, NO integrado a `voice_live.py` ni
al flujo real — conecta al WS de Deepgram Agent, configura DeepSeek como
`think` y `cotizar` como función `client_side`, mide tiempos con audio de
prueba grabado (repetible, no llamada en vivo).

## Affected Areas

| Area | Impact | Description |
|------|--------|--------------|
| `apps/ai/scripts/voice_agent_spike.py` | New | Script de validación, descartable |
| `apps/ai/app/voice_live.py` | None | Sin cambios — el spike es standalone |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| DeepSeek no conecta bien como LLM custom (no managed) | Med | Es justo lo que mide el spike |
| `functions` no calza 1:1 con `TOOLS_SCHEMA` (OpenAI tools) | Med | Probar con una sola herramienta simple primero |
| Consume cuota de Deepgram sin resultado útil | Low | Acotado a una sesión corta, no un loop continuo |

## Rollback Plan

Es un script aislado y descartable — no toca código de producción. Si no
sirve, se borra el archivo y no queda ningún rastro en `voice_live.py`.

## Dependencies

- Cuenta Deepgram con acceso al Voice Agent (Agents Platform) habilitado.

## Success Criteria

- [x] El script conecta y recibe `Welcome`+`SettingsApplied` con DeepSeek configurado.
- [x] `cotizar` se ejecuta vía `FunctionCallRequest`/`FunctionCallResponse` correctamente (contra Postgres real).
- [x] Latencia medida: ~1.9s a primer audio, ~3.7s a `FunctionCallRequest` (un turno de prueba, `deepseek-v4-flash`).
- [x] Recomendación: ver `RESULTADOS MEDIDOS` en el docstring de `voice_agent_spike.py` — datos suficientes para decidir, sin baseline exacto del sistema actual para comparar 1:1 (no se midió con el mismo método).

## Hallazgo fuera de alcance (bug real de producción)

DeepSeek deprecó el modelo `"deepseek-chat"` (API devuelve 400). Corregido
el default de `DEEPSEEK_MODEL` en `apps/ai/app/config.py` a
`deepseek-v4-flash` — cualquier `.env` sin este override tenía TODAS las
llamadas reales a DeepSeek rotas (voz, chat web, WhatsApp).
