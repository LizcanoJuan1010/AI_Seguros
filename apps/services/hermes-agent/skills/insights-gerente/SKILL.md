---
name: insights-gerente
description: Insights de negocio para usuarios gerentes - KPIs, funnel, ventas por país y producto, leads recientes y dashboards Metabase. Usar solo con rol verificado gerente.
---

# Insights para gerentes

**Antes de todo**: confirma el rol con
`GET ${SEGURIA_API_URL:-http://localhost:8085}/api/roles/{telefono}` (header `X-Service-Key: $SERVICE_API_KEY`).
Si no es `gerente`, no uses esta skill ni reveles datos de negocio.

## Datos disponibles
```bash
# KPIs, funnel, por país, por producto, serie temporal, dashboards Metabase
curl -s ${SEGURIA_API_URL:-http://localhost:8085}/api/insights/summary -H "X-API-Key: $MANAGER_API_KEY"

# Últimos 100 leads con cotizaciones y prima
curl -s ${SEGURIA_API_URL:-http://localhost:8085}/api/insights/leads -H "X-API-Key: $MANAGER_API_KEY"
```

## Cómo responder
- No vuelques el JSON: analiza. Responde la pregunta del gerente con 3-5 datos clave,
  una comparación relevante (vs. otro país/producto) y una recomendación accionable.
- Tablas de texto simples para comparativas; números con separador de miles.
- Si `metabase.enabled` es true, incluye el enlace del dashboard relevante.
- Si piden un informe formal o una presentación ejecutiva, usa la skill
  `presentaciones-seguros`.

Ejemplos de preguntas que debes poder responder: "¿cómo va la conversión este mes?",
"¿qué producto se vende más en Colombia?", "¿dónde estamos perdiendo leads en el
funnel?", "dame la prima total vendida por país".
