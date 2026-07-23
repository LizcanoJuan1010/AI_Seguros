---
name: siniestros
description: Reclamos / siniestros (FNOL) por WhatsApp - reportar un siniestro de una póliza vigente, consultar su estado y guiar los documentos de soporte. Usar cuando el cliente diga que le pasó algo (choque, robo, enfermedad, daño) o pregunte por su reclamo.
---

# Siniestros (FNOL por WhatsApp)

Cierra el ciclo venta → póliza → **siniestro**. Primero empatía, luego proceso.

## Flujo de reporte
1. **Empatía primero**: pregunta si la persona está bien antes de pedir datos.
2. Pide el **número de póliza** (`POL-...`) y **qué pasó** (en sus palabras).
   Opcionales: fecha del incidente y pérdida estimada en COP.
3. Registra el reclamo:
```bash
curl -s -X POST ${SEGURIA_API_URL:-http://localhost:8085}/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"<phone>","message":"<relato del cliente>","phone":"<phone>"}'
```
   (el orquestador usa la herramienta `reportar_siniestro`; también puedes
   llamarla explícitamente pidiéndole "reporta el siniestro de la póliza X").
4. Confírmale el **número de reclamo** (`CLM-...`) y la lista de **documentos
   de soporte** que devuelve la herramienta. El cliente puede enviarlos como
   fotos/PDF por WhatsApp: Hermes los sube con `POST /api/assistant/upload` y
   pasa los `file_ids` al reporte.

## Seguimiento
- "¿Cómo va mi reclamo?" → herramienta `estado_siniestro(claim_number)`.
- Explica el estado en lenguaje simple: reportado = recibido · en_revision =
  un analista lo evalúa · docs_pendientes = faltan documentos · aprobado/pagado
  = buena noticia · rechazado = explica con empatía y ofrece escalar a asesor.

## Reglas
- Solo pólizas **vigentes** pueden reclamar; si no aparece la póliza, verifica
  el número antes de decir que no existe.
- Las **banderas de fraude** del triage son INTERNAS del equipo: nunca se
  mencionan al cliente (el gerente las ve en su panel).
- Nunca prometas plazos de pago ni montos de indemnización: eso lo confirma el
  analista humano.
