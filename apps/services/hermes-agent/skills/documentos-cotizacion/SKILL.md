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
   **`file_path` es una ruta DENTRO del contenedor `seguria-api` — Hermes corre en
   su propio contenedor, sin ese filesystem montado. NUNCA intentes leer, buscar
   (`find`) ni acceder a `file_path` directamente: siempre va a fallar.**
3. Descarga el PDF a un archivo temporal local vía `download_url` (esa sí es una
   URL HTTP real, servida por `seguria-api`):
```bash
curl -s -o /tmp/cotizacion_<QUOTE_ID>.pdf "${SEGURIA_API_URL:-http://localhost:8085}<DOWNLOAD_URL>"
```
4. Envía ese archivo local (`/tmp/cotizacion_<QUOTE_ID>.pdf`) como documento adjunto
   en WhatsApp (no pegues la ruta ni la URL en el chat). Acompáñalo con un mensaje
   breve: qué contiene y el siguiente paso.
5. El endpoint del paso 2 ya mueve el lead a etapa `documento`; no dupliques la
   actualización.

Nunca afirmes que el documento fue enviado sin haber ejecutado el paso 2 y adjuntado
el archivo real.
