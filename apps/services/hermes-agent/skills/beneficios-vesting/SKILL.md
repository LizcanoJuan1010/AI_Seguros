---
name: beneficios-vesting
description: Libera los beneficios de permanencia (parque en el mes 3, droguería en el mes 6, hotel en el mes 12 de póliza vigente continua — "la póliza que sí se usa"). Usar en un cron diario.
---

# Beneficios de vesting (inventario perecedero)

El costo de adquisición no se paga con un descuento al comprar: se paga con
capacidad ociosa de Colsubsidio (parques, droguerías, hoteles), liberada
ESCALONADA por meses de póliza vigente y sin interrupción. Solo se entrega si
la póliza sobrevivió — ataca de frente la caída de cartera en los primeros
meses, que es el problema real (no la venta inicial). Ver
`Nota_estrategica_Seguros_Colsubsidio.pdf` §4.

## Configurar el cron (una sola vez)
En Hermes: `programa una tarea diaria a las 08:00 que ejecute la skill
beneficios-vesting`.

## Ejecución
```bash
curl -s -X POST ${SEGURIA_API_URL:-http://localhost:8085}/api/benefits/check \
  -H "X-Service-Key: $SERVICE_API_KEY"
```
La respuesta trae `entregados`: lo que se desbloqueó HOY (el endpoint ya es
idempotente — no reentrega lo ya dado). El aviso al cliente por WhatsApp y la
alerta informativa al gerente ya los manda el propio endpoint; esta skill solo
dispara el chequeo diario, no tiene que redactar ni enviar nada más.

## Notas
- No hay límite anti-spam que aplicar aquí (a diferencia de
  `seguimiento-proactivo`/`reactivar-checklist`): esto no es contacto
  comercial nuevo, es la confirmación de un beneficio ya ganado.
- Si un cliente pregunta por sus beneficios en el chat, esa pregunta la
  resuelve la tool `consultar_beneficios` del agente conversacional
  (Sofía/Mónica/Camila), no esta skill.
