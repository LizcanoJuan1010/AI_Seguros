"""Motor de versionado/QA de prompts (adaptado de docket-motor,
https://github.com/neylinsomne/docket-motor, bases 01-06) para los prompts de
Tequendama (`SYSTEM_PROMPT_WEB`/`SYSTEM_PROMPT_WHATSAPP`/`SYSTEM_PROMPT_GERENTE`
en `agent_core.py`).

Reusa la misma base de Supabase que el resto de Tequendama, en un schema
propio (`docket`, ver la migración `20260724160000_docket_engine_core`) —
mismo patrón de separación por schema que ya existe entre `public` (Prisma) y
`seguria` (Python). Sin monitoreo en vivo: la pieza de "Stance Engine" del
repo original es enterprise-only en ElevenLabs y se descartó para este
proyecto; esto solo versiona/mejora el prompt, no cambia nada mid-call.

Todo detrás de `DOCKET_ENGINE_ENABLED` (default False) — mismo criterio
fail-open que el resto del stack (ElevenLabs/WA gateway/Polar): sin esto
activado, el proyecto opera exactamente igual que antes.
"""
