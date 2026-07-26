---
name: reactivar-checklist
description: Reactivación por LLAMADA (Camila) de leads calientes con el checklist de activación (identidad→firma→pago) estancado. Usar en el cron diario, aparte de seguimiento-proactivo (ese es texto; este es llamada de voz).
---

# Reactivar checklist estancado

Un lead que ya llegó al checklist de activación (`generar_checklist_activacion`)
está más caliente que uno en descubrimiento: ya eligió, ya dio consentimiento.
Si se estanca sin avanzar de paso ni pagar, el contacto correcto es una
llamada de Camila, no un mensaje de texto más (eso ya lo cubre
`seguimiento-proactivo` para leads fríos).

## Configurar el cron (una sola vez)
En Hermes: `programa una tarea cada 6 horas que ejecute la skill
reactivar-checklist`. Más frecuente que `seguimiento-proactivo` (10:00 diario)
porque un checklist pagado a medias es más urgente que un lead frío.

## Ejecución
1. Trae los nudges accionables:
```bash
curl -s ${SEGURIA_API_URL:-http://localhost:8085}/api/proactive -H "X-API-Key: $MANAGER_API_KEY"
```
2. Filtra SOLO `tipo == "checklist_estancado"` de `nudges_clientes` (el resto
   de tipos los maneja `seguimiento-proactivo`, no los toques aquí).
3. Por cada uno, dispara la llamada real (no un mensaje):
```bash
curl -s -X POST ${SEGURIA_API_URL:-http://localhost:8085}/api/calls/checklist \
  -H "X-Service-Key: $SERVICE_API_KEY" -H "Content-Type: application/json" \
  -d "{\"phone\": \"$PHONE\", \"tenant_id\": \"$TENANT_ID\"}"
```
Esto reenvía primero el link vigente del checklist (rota el token, el anterior
deja de servir) y luego llama con Camila, quien ya sabe en qué paso quedó el
cliente (`paso_checklist`/`dias_sin_avanzar` en sus variables de la llamada).

## Límites anti-spam (obligatorios)
- Máximo UNA llamada de reactivación por cliente por día.
- Ventana legal (Ley 2300 de 2023, Colombia): SOLO lunes a viernes 7:00–19:00
  y sábados 8:00–15:00, hora de Colombia — nunca domingo. `calls.py` ya la
  aplica del lado del servidor (`iniciar_llamada` rechaza fuera de esa
  franja), pero no dispares la skill fuera de ella de todos modos.
- Si Camila registra que el cliente pidió no ser contactado más: marca etapa
  `perdido` (`POST /api/leads`, header `X-Service-Key: $SERVICE_API_KEY`) y no
  vuelvas a incluirlo ni aquí ni en `seguimiento-proactivo`.
