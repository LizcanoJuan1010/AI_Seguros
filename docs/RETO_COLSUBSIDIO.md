# Reto Colsubsidio 30X — Venta automatizada de seguros

> Misión: llevar a una persona desde **"no sé qué seguro necesito"** hasta
> **"ya quedé asegurada"** SIN hablar con nadie, por WhatsApp.
> Flujo: **detectar el momento → presentar la oferta → CERRAR la venta**.
> Colsubsidio es **distribuidor** (no fabrica pólizas, las distribuye), 24/7 y escalable.

## Validación / análisis de brechas

| Etapa | Estado | Acción |
|---|---|---|
| Detectar momento/necesidad | 🟡 conversacional (SPIN) | añadir disparadores de "momento" (entrada proactiva) |
| Presentar oferta | 🟢 cotizador + 3 opciones + PDF | — |
| Explicar / objeciones | 🟢 | — |
| **Cerrar la venta** | 🔴 falta | **construir flujo de cierre/emisión (foco de esta fase)** |
| Sin humano | 🔴 postura "pre-venta" | reformular a **cierre autónomo** |
| 24/7 / escala / WhatsApp | 🟢 arquitectura nueva | cablear cierre por WhatsApp |

## Diseño del cierre autónomo (de cotización → póliza)

Reusa el esquema de Tequendama `Customer → Lead → Quote → Policy`. El cierre crea esa
cadena, con consentimiento, y devuelve el número de póliza.

Pasos (todos en el chat, sin humano):
1. Cliente elige una opción cotizada.
2. **Captura de datos** para emitir: nombre completo, tipo+número de documento (CC),
   fecha de nacimiento, email, ciudad. (→ `Customer`).
3. **Consentimiento habeas data** (Ley 1581/2012, Colombia): explícito y registrado
   (`Customer.consentData=true`, `consentAt`). Obligatorio para continuar.
4. **Pago**: link/método (para el demo: `simulado`; en real PSE/tarjeta). Registrado.
5. **Emisión de póliza**: crear `Policy` (número, vigencia +1 año, `status=vigente`,
   prima). Colsubsidio distribuye; la aseguradora emite → aquí se registra + confirma.
6. **Confirmación "ya quedé asegurada"**: mensaje + **PDF de la póliza** (carátula/
   certificado con número, aseguradora, coberturas, vigencia) + número de póliza.
7. Derecho de **retracto** (Ley 1480/2011) informado. Takeover humano solo si lo pide.

## Contrato: `POST /api/v1/checkout` (backend NestJS)

Request:
```json
{
  "customer": {"fullName":"Ana Torres","documentType":"CC","documentId":"1032456789",
               "birthDate":"1990-05-12","email":"ana@mail.com","phone":"+573001112233",
               "city":"Bogotá","department":"Cundinamarca"},
  "consentData": true,
  "insuranceType": "VIDA",
  "monthlyPremiumCop": 45000,
  "coverage": {"resumen":"..."},
  "payment": {"method":"simulado","reference":"demo"},
  "leadId": null
}
```
Comportamiento (una transacción Prisma):
- Rechaza con 400 si `consentData !== true`.
- **Upsert `Customer`** por (`documentType`,`documentId`); fija `consentData=true`,
  `consentAt=now()`.
- Mapea `insuranceType` → producto sembrado (VIDA→Vida Esencial, AUTO→Auto Total,
  SALUD→Salud Integral).
- Crea `Lead` (`status=cerrado_ganado`, `closedAt=now`) → `Quote` (`status=aceptada`) →
  `Policy` (`policyNumber` generado, `startDate=now`, `endDate=+1año`, `status=vigente`,
  `monthlyPremiumCop`).
Response:
```json
{"policyNumber":"POL-2026-000123","policyId":"uuid","customerId":"uuid",
 "status":"vigente","startDate":"...","endDate":"...","insuranceType":"VIDA",
 "monthlyPremiumCop":45000}
```

## Contrato SSE ampliado (servicio IA → frontend)

Nuevo evento además de los de FUSION.md:
| event | data | UI |
|---|---|---|
| `checkout_step` | `{"step":"datos\|consentimiento\|pago\|emision","fields"?:[...]}` | guía el cierre (formulario-en-chat / confirmación) |
| `policy` | `{"policyNumber":"POL-...","download_url":"/api/documents/poliza_....pdf","title":"Póliza vigente"}` | tarjeta verde "Ya quedaste asegurada" + descargar |

## Herramientas nuevas del orquestador (servicio IA)
- `capturar_datos_cliente(fullName, document_id, birth_date, email, city)` — valida y guarda en sesión.
- `registrar_consentimiento(acepta: bool)` — habeas data; sin `true` no se emite.
- `emitir_poliza(insurance_type, monthly_premium_cop, coverage, customer, payment)` —
  llama `POST /api/v1/checkout`, genera el **PDF de póliza** y emite el evento `policy`.

## Reformulación de cumplimiento (cierre autónomo)
- Tequendama **cierra sola**; Colsubsidio distribuye; la aseguradora emite.
- Consentimiento habeas data **obligatorio** y registrado antes de emitir.
- Divulgación clara de aseguradora, coberturas, exclusiones y prima.
- Derecho de **retracto** informado. Datos mínimos (no historial médico innecesario).
- Takeover humano **solo si el cliente lo pide** (no como paso obligatorio del cierre).

## Detección del momento (mejora de "detecta el momento")
Entrada por: (a) inbound WhatsApp con detección de intención; (b) campañas proactivas
por evento de vida (compró carro→auto, viaje próximo→viaje, nuevo hijo→vida/salud)
apoyadas en el motor `proactive.py`. Foco de esta fase: el CIERRE; el momento se cubre
con la entrada conversacional + un gancho proactivo.

## Métrica de eficiencia (objetivo del reto)
Minimizar turnos de "no sé" → "asegurada". Meta: **≤ 8 turnos** en el happy path
(descubrir 2-3, cotizar 1, elegir 1, datos 1, consentimiento+pago 1, emisión 1).
