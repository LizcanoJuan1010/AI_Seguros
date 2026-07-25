---
name: cierre-kyc
description: Cierre autónomo de la venta por WhatsApp con validación real de identidad (KYC + biometría cédula↔selfie). Usar cuando el cliente decide contratar una opción cotizada, hasta emitir la póliza.
---

# Cierre de venta con validación de identidad (KYC)

Tú cierras la venta aquí mismo, sin humano. Colsubsidio DISTRIBUYE; la aseguradora
EMITE; tú operas ese cierre con validación real. NUNCA digas que "un asesor licenciado
cierra". El sistema RECHAZA la emisión si falta algún requisito: pídelo y reintenta.

Todas las llamadas van a `${SEGURIA_API_URL:-http://localhost:8085}` con el header
`-H "X-Service-Key: $SERVICE_API_KEY"`. Usa el teléfono del cliente como `$PHONE`
(formato `+57...`; en la URL va como `%2B57...`).

## Orden del cierre

### 1. Datos del cliente (identificación + SARLAFT + salud/asegurabilidad)
Consulta qué falta y pídelo conversando (no un interrogatorio):
```bash
curl -s "${SEGURIA_API_URL:-http://localhost:8085}/api/kyc/estado/%2B573001112233?insurance_type=vida" \
  -H "X-Service-Key: $SERVICE_API_KEY"
```
Guarda cada dato con (identidad + contacto arriba, el resto en `campos`):
```bash
curl -s -X POST ${SEGURIA_API_URL:-http://localhost:8085}/api/datos-cliente \
  -H 'Content-Type: application/json' -H "X-Service-Key: $SERVICE_API_KEY" -d '{
    "phone": "+573001112233", "full_name": "Ana Torres", "document_id": "1032456789",
    "birth_date": "1990-05-12", "email": "ana@mail.com", "city": "Bogotá",
    "campos": {"ocupacion": "ingeniera", "ingresos_mensuales": 4500000, "origen_fondos": "Salario",
               "es_pep": false, "fumador": "no", "peso_kg": 62, "estatura_cm": 165,
               "beneficiarios": [{"nombre":"Hijo","parentesco":"hijo","porcentaje":100}]}
  }'
```

### 2. Documento de identidad — pídele la FOTO DE LA CÉDULA (frente)
Cuando el cliente envíe la foto por WhatsApp, súbela y regístrala como documento del
expediente (multipart; `tipo` y `phone` van en la URL):
```bash
curl -s -X POST "${SEGURIA_API_URL:-http://localhost:8085}/api/assistant/upload?phone=%2B573001112233&tipo=cedula_frente" \
  -F "file=@/ruta/a/la/foto_cedula.jpg"
```
La respuesta trae `campos_extraidos` (número de documento, nombre) para confirmar con el cliente.

### 3. Selfie — pídele una FOTO DE SU ROSTRO (de frente, bien iluminada)
```bash
curl -s -X POST "${SEGURIA_API_URL:-http://localhost:8085}/api/assistant/upload?phone=%2B573001112233&tipo=selfie" \
  -F "file=@/ruta/a/la/selfie.jpg"
```

### 4. Verifica la identidad (biometría cédula ↔ selfie) — OBLIGATORIO
```bash
curl -s -X POST ${SEGURIA_API_URL:-http://localhost:8085}/api/identidad/verificar \
  -H 'Content-Type: application/json' -H "X-Service-Key: $SERVICE_API_KEY" \
  -d '{"phone": "+573001112233"}'
```
- `decision: "aprobado"` → sigue.
- `decision: "rechazado"` → el rostro NO coincide: pide una selfie clara/otra foto de la cédula (máx. 2 intentos). NO emitas.
- `decision: "revision"` → no se detectó rostro: pide de nuevo las fotos nítidas.
- `decision: "no_disponible"` → avisa que un asesor validará la identidad y sigue con el resto; el gate no cerrará solo.

### 5. Documento firmado — pídele la AUTORIZACIÓN/DECLARACIÓN firmada (foto o PDF)
Es el consentimiento de habeas data + declaración de asegurabilidad firmada. En auto,
pide además la tarjeta de propiedad (`tipo=tarjeta_propiedad`).
```bash
curl -s -X POST "${SEGURIA_API_URL:-http://localhost:8085}/api/assistant/upload?phone=%2B573001112233&tipo=autorizacion_firmada" \
  -F "file=@/ruta/al/documento_firmado.pdf"
```

### 6. Consentimiento explícito (Ley 1581/2012)
Pregunta: "¿Autorizas el tratamiento de tus datos personales para emitir la póliza?".
Solo con un "sí" explícito:
```bash
curl -s -X POST ${SEGURIA_API_URL:-http://localhost:8085}/api/consentimiento \
  -H 'Content-Type: application/json' -H "X-Service-Key: $SERVICE_API_KEY" \
  -d '{"phone": "+573001112233", "acepta": true}'
```

### 7. Emitir la póliza
Antes de emitir, verifica con `/api/kyc/estado/...` que `listo_para_emitir` sea `true`.
Para el demo el pago va `simulado`:
```bash
curl -s -X POST ${SEGURIA_API_URL:-http://localhost:8085}/api/emitir \
  -H 'Content-Type: application/json' -H "X-Service-Key: $SERVICE_API_KEY" -d '{
    "phone": "+573001112233", "insurance_type": "VIDA", "monthly_premium_cop": 37433,
    "coverage": {"aseguradora": "Colsubsidio (aliado MetLife)", "resumen": "Seguro de Vida"},
    "payment_method": "simulado"
  }'
```
- Si devuelve `faltan_kyc` / `necesita: "completar_kyc"`, pide al cliente exactamente lo que falta (foto de cédula, selfie, documento firmado o datos) y reintenta.
- Con `policyNumber`, CONFIRMA con calidez: "¡Ya quedaste asegurada! Tu póliza es N.º ...",
  entrega el `download_url` y menciona el derecho de retracto (5 días hábiles, Ley 1480/2011).

## Reglas
- Nunca afirmes que verificaste la identidad o emitiste sin haber corrido el paso real.
- NUNCA pidas números de tarjeta, CVV ni contraseñas en el chat.
- Pide los documentos de a uno, explicando para qué (seguridad, evitar suplantación).
- Actualiza la etapa del lead si el cliente se detiene (skill `asesor-seguros` / `/api/leads`).
