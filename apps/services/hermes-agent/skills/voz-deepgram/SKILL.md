---
name: voz-deepgram
description: Transcribe o genera notas de voz vía Deepgram (seguria-ai). Alternativa a STT integrado/skill `voz` (Kokoro) — usar solo si el cliente lo pide explícito o si Kokoro falla.
---

# Voz (Deepgram, vía seguria-ai)

Dos endpoints en `${SEGURIA_API_URL:-http://localhost:8085}`, header `X-Service-Key: $SERVICE_API_KEY`.

## Transcribir (nota de voz -> texto)
```bash
curl -s -X POST ${SEGURIA_API_URL:-http://localhost:8085}/api/voice/transcribe \
  -H "X-Service-Key: $SERVICE_API_KEY" -F "file=@nota.ogg;type=audio/ogg"
```
Devuelve `{"texto": "...", "idioma": "es"}`.

## Generar (texto -> nota de voz)
```bash
curl -s -X POST ${SEGURIA_API_URL:-http://localhost:8085}/api/voice/generar \
  -H "Content-Type: application/json" -H "X-Service-Key: $SERVICE_API_KEY" \
  -d '{"texto":"Hola, tu cotización está lista."}'
```
Devuelve `{"audio_url": "/api/voice/audio/..."}` — descarga esa ruta y mándala como nota de voz.

No narres la llamada al tool. Igual que `voz`: audio corto y complementario, cifras exactas siempre también en texto.
