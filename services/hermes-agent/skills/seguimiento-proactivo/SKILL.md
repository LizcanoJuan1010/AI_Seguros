---
name: seguimiento-proactivo
description: Seguimiento proactivo de leads (estilo Erica - el asistente inicia la conversación). Usar en el cron diario de seguimiento y cuando un gerente pida "activa los seguimientos".
---

# Seguimiento proactivo

La mayoría de las ventas se cierran en el seguimiento, no en el primer contacto
(en Erica, 50-60% de las interacciones nacen de una sugerencia proactiva).

## Configurar el cron (una sola vez)
En Hermes: `programa una tarea diaria a las 10:00 que ejecute la skill
seguimiento-proactivo`.

## Ejecución
1. Trae los seguimientos accionables:
```bash
curl -s ${SEGURIA_API_URL:-http://localhost:8085}/api/proactive -H "X-API-Key: $MANAGER_API_KEY"
```
2. Por cada `nudge` de `nudges_clientes` (respetando prioridad alta → baja):
   - Redacta un mensaje corto y personal según `tipo`:
     - `seguimiento_cotizacion`: retoma SU cotización concreta (producto y prima del
       `contexto`), pregunta si quedó alguna duda u ofrece ajustar la suma.
     - `cierre_pendiente`: ofrece agendar la llamada con el asesor licenciado.
     - `retomar_descubrimiento`: UNA pregunta concreta sobre su necesidad
       (nunca un genérico "¿sigues ahí?").
   - Envíalo por WhatsApp al `phone` del nudge y registra el mensaje en
     `POST /api/conversations` (header `X-Service-Key: $SERVICE_API_KEY`) con role `asistente`.
3. Las `alertas_gerente` NO van a clientes: resúmelas en un solo mensaje al gerente
   (números de teléfono en `MANAGER_PHONES`) solo si hay alguna con prioridad alta.

## Límites anti-spam (obligatorios)
- Máximo UN mensaje proactivo por cliente por día, y máximo 3 por cotización.
- Nunca proactivo antes de las 9:00 ni después de las 20:00 hora local del país.
- Si el cliente respondió "no me interesa" o similar: marca etapa `perdido`
  (`POST /api/leads`, header `X-Service-Key: $SERVICE_API_KEY`) y no vuelvas a contactarlo.
