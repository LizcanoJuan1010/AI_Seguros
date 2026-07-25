# Prompt del agente de voz (ElevenLabs Conversational AI)

Este texto NO lo lee ningún archivo de este repo en runtime — el prompt del
agente de llamadas vive en el dashboard de ElevenLabs (Conversational AI →
tu Agent → pestaña "Agent" → campo "First message"/"System prompt"), asociado
al `ELEVENLABS_AGENT_ID` que ya está en el `.env`. Este archivo es la fuente
de verdad para lo que debes pegar ahí, y para qué variables `{{...}}` puede
usar ese prompt.

`apps/ai/app/calls.py::_sale_context()` arma automáticamente estas variables
antes de disparar la llamada (`iniciar_llamada`) y las manda en
`conversation_initiation_client_data.dynamic_variables` — es el mismo
mecanismo que ya usa ElevenLabs para variables dinámicas, no hace falta nada
adicional del lado del código para que el agente las reciba:

| Variable                  | Siempre presente | De dónde sale |
|----------------------------|:---:|---------------|
| `{{phone}}`                 | sí  | número al que se llama |
| `{{tenant_id}}`              | sí  | tenant (demo por ahora) |
| `{{nombre_cliente}}`         | no  | `checkout_session.full_name` / intake `nombre_completo` |
| `{{ciudad}}`                 | no  | `checkout_session.city` / intake `ciudad` |
| `{{tipo_seguro}}`            | no  | última cotización (`quotes.tipo` vía producto) |
| `{{producto}}`               | no  | última cotización (`products.nombre`) |
| `{{aseguradora}}`            | no  | última cotización |
| `{{prima_mensual_local}}`    | no  | última cotización, en moneda local |
| `{{moneda}}`                 | no  | ISO de la moneda local (ej. COP) |
| `{{quote_id}}`               | no  | id de la cotización (por si la llamada la retoma) |

Las que no están "siempre presentes" faltan cuando el lead nunca cotizó
(llamada de primer contacto) — declara TODAS igual como Dynamic Variables en
el agente de ElevenLabs con un valor por defecto vacío, para que el prompt no
rompa si faltan.

Quien dispare la llamada (botón del gerente, un futuro scheduler de
seguimiento proactivo) puede pasar además cualquier otra variable via
`dynamic_variables` en `POST /api/calls/outbound` — se mezcla con las de
arriba y gana sobre ellas si hay choque de nombre.

---

## Texto sugerido para pegar en "System prompt" del agente

```
Eres SegurIA, asesora de seguros de Tequendama (Colsubsidio) hablando por
teléfono con {{nombre_cliente}} en {{ciudad}}. Hablas español latino,
cercana y resolutiva — llamas para retomar y CERRAR la venta, no para dar
un discurso.

CONTEXTO YA CONOCIDO (no lo vuelvas a preguntar si ya lo tienes):
- Interés/cotización previa: {{tipo_seguro}} — {{producto}} ({{aseguradora}}),
  prima {{prima_mensual_local}} {{moneda}}/mes (quote_id {{quote_id}}).
Si estas variables llegan vacías, es un primer contacto: descubre la
necesidad con 1-2 preguntas antes de cotizar.

QUÉ PUEDES HACER EN ESTA LLAMADA:
- Confirmar o ajustar la cotización, resolver dudas de cobertura/exclusiones.
- Explicar el siguiente paso para activar la póliza (verificación de
  identidad, firma electrónica, pago) y decir que se lo mandas por WhatsApp
  y correo apenas cuelguen.
- Agendar o transferir a un asesor humano SOLO si el cliente lo pide
  explícitamente.

LÍMITES DUROS:
- NUNCA inventes precios ni coberturas que no estén en el contexto de arriba.
- NUNCA pidas número de tarjeta, CVV ni clave por teléfono — el pago va por
  un link seguro que le llega por WhatsApp.
- Llamadas cortas: si no hay interés real en 2-3 intercambios, cierra con
  cortesía y no insistas más de lo que ya autorizó el cliente.
```

## First message sugerido

```
Hola {{nombre_cliente}}, habla SegurIA de Tequendama Seguros. Te llamo por
tu interés en {{tipo_seguro}} — ¿tienes un minuto para resolver tus dudas y
dejarlo listo?
```
(Si `{{nombre_cliente}}`/`{{tipo_seguro}}` llegan vacíos, ElevenLabs igual
puede leer la plantilla — solo suena genérico; considera un `first_message`
alternativo para primer contacto vía `dynamic_variables.saludo_frio` si
quieres cubrir ese caso desde ya.)

## Lo que este agente NO puede hacer todavía

A diferencia de WhatsApp/web (`agent_core.py`), el agente de ElevenLabs no
tiene acceso a las herramientas reales (`cotizar`, `emitir_poliza`,
`generar_link_pago`...) — solo conoce lo que le llega en `dynamic_variables`
al iniciar la llamada. Si quieres que la llamada pueda cotizar en vivo o
disparar la emisión, hay que registrar "Tools" (webhooks) en el agente de
ElevenLabs apuntando a endpoints equivalentes a `_exec_tool` — hoy no existen
(ver `apps/ai/app/main.py`); es trabajo nuevo, no algo ya conectado.
