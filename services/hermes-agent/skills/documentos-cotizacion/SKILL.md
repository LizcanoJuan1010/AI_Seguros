---
name: documentos-cotizacion
description: Genera la cotización formal en PDF de una opción cotizada y la envía por WhatsApp. Usar cuando el cliente elige una opción o pide "mándame la cotización".
---

# Documentos de cotización

1. Toma el `quote_id` de la opción elegida (viene en la respuesta de `POST /api/quotes`).
2. Genera el PDF:
```bash
curl -s -X POST ${SEGURIA_API_URL:-http://localhost:8085}/api/quotes/<QUOTE_ID>/document
```
   Respuesta: `{"file_path": "/ruta/al/pdf", "download_url": "/api/documents/..."}`.
3. Envía el archivo `file_path` como documento adjunto en WhatsApp (no pegues la ruta
   en el chat). Acompáñalo con un mensaje breve: qué contiene y el siguiente paso.
4. El endpoint ya mueve el lead a etapa `documento`; no dupliques la actualización.

Nunca afirmes que el documento fue enviado sin haber ejecutado el paso 2 y adjuntado
el archivo real.
