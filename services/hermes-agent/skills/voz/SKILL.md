---
name: voz
description: Responde con notas de voz usando Kokoro-FastAPI (TTS local, API OpenAI-compatible). Usar cuando el cliente envió audio, pide voz, o el mensaje es una bienvenida/resumen personal.
---

# Voz (Kokoro-FastAPI TTS)

TTS local en `http://localhost:8880` (API compatible con OpenAI Audio). Las notas de
voz **entrantes** ya llegan transcritas por Hermes (STT integrado); esta skill es para
**responder** con audio en español latino.

Levantar el servicio (una sola vez; ver `scripts/setup.sh voz`):
```bash
docker run -d --name seguria-tts --restart unless-stopped \
  -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

## Generar audio
```bash
curl -s -X POST http://localhost:8880/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"model":"kokoro","input":"Hola, soy SegurIA. Tu cotización está lista.",
       "voice":"ef_dora","response_format":"mp3","speed":1.0}' \
  --output respuesta.mp3
```
- Voces en español: `ef_dora` (femenina, recomendada para SegurIA), `em_alex`, `em_santa`.
- Convierte a nota de voz de WhatsApp si el canal lo requiere:
  `ffmpeg -i respuesta.mp3 -c:a libopus respuesta.ogg`.

## Criterio
- Audio ≤ 45 segundos: resume, no leas tablas ni listas de precios completas.
- Las cifras exactas van SIEMPRE también en texto (el audio complementa, no reemplaza).
- Si el servicio no responde (`curl -s localhost:8880/v1/audio/voices` falla), continúa
  solo con texto y no bloquees la conversación.

## Máxima naturalidad (opcional, estilo Sesame)
Si más adelante quieres voz conversacional tipo Sesame, se puede sustituir el endpoint
por Sesame CSM-1B (requiere GPU con VRAM libre y nvidia-container-toolkit). Kokoro es la
opción por defecto por ser ligera, en español y correr en CPU sin toolkit.
