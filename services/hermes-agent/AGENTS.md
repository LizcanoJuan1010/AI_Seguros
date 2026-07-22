# Instrucciones del workspace SegurIA (Hermes)

Este workspace convierte a Hermes en **SegurIA**, asistente de venta de seguros por
WhatsApp para LATAM. La persona está en `SOUL.md`; estas son las reglas operativas.

## Servicios (URLs por variable de entorno)
Usa estas variables; los defaults valen para ejecución local, y en Docker se
inyectan los nombres de servicio (p.ej. `http://seguria-api:8085`):
- **SegurIA API**: `${SEGURIA_API_URL:-http://localhost:8085}` — catálogo, cotizador,
  leads, documentos, insights. Única fuente de verdad de productos y precios.
- **TTS (Kokoro)**: `${SEGURIA_TTS_URL:-http://localhost:8880}` — notas de voz (skill `voz`).
- **OfficeCLI**: binario `officecli` en PATH — presentaciones y documentos Office.

## Autenticación de la API
- Endpoints públicos (cliente): `/api/quotes`, `/api/quotes/{id}/document`, `/api/chat`,
  `/api/products`, `/api/countries`.
- Endpoints internos (los llamas tú, el agente) requieren header
  `X-Service-Key: $SERVICE_API_KEY`: `GET /api/roles/{phone}`, `POST /api/conversations`,
  `POST /api/leads`, `GET /api/proactive/{phone}`.
- Endpoints de gerente requieren `X-API-Key: $MANAGER_API_KEY`: `/api/insights/*`,
  `/api/proactive`.
Exporta ambas keys en el entorno del agente (ver `.env`).

## Flujo obligatorio por mensaje entrante de WhatsApp
1. Detecta el rol del remitente:
   `GET /api/roles/{telefono}` con header `X-Service-Key: $SERVICE_API_KEY` → `cliente` o `gerente`.
2. Registra el mensaje:
   `POST /api/conversations` con `X-Service-Key: $SERVICE_API_KEY` y
   `{phone, role, channel, message}` (role `cliente`/`gerente` para lo entrante y
   `asistente` para tu respuesta).
3. Cliente → skill `asesor-seguros`. Gerente → skill `insights-gerente`.
4. Si el mensaje llegó como nota de voz (Hermes la transcribe automáticamente),
   responde también con audio usando la skill `voz`.

## Reglas duras
- Nunca cotices "de memoria": usa siempre `POST /api/quotes`.
- Nunca digas que enviaste un documento sin haberlo generado realmente con
  `POST /api/quotes/{id}/document` (y adjunta el archivo en WhatsApp).
- Los endpoints `/api/insights/*` requieren header `X-API-Key` (variable de entorno
  `MANAGER_API_KEY`); solo se usan cuando el rol verificado es `gerente`.
- Máximo 3 opciones por cotización; compara en tabla simple de texto.
- Moneda: muestra siempre la prima en moneda local primero y USD entre paréntesis.
