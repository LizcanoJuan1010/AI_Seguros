"""Orquestador agéntico de Tequendama: loop de function calling multi-ronda con DeepSeek.

Patrón tomado del orquestador de referencia (Paloma core/agents.py), reducido a lo
esencial y con sus dos lecciones clave:
  1. Las herramientas son la única fuente de precios/documentos (payloads
     estructurados y validados; el modelo nunca inventa cifras).
  2. Red de seguridad de documentos: si el modelo afirma haber enviado una
     cotización sin haber llamado la herramienta, se fuerza la corrección.

El canal principal (WhatsApp) lo orquesta Hermes con las skills; este módulo da la
misma capacidad agéntica al canal web (SPA) y sirve de fallback API-first.
"""
import json
import logging
import re
from typing import Any

import psycopg

from .config import (BACKEND_URL, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL,
                     DEEPSEEK_MODEL, MANAGER_PHONES)
from .db import COUNTRY_NAMES, get_conn
from .documents import build_policy_pdf, build_quote_pdf
from .insights import summary as insights_summary
from .quoting import recommend

log = logging.getLogger("seguria.agent")

MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT_CLIENTE = """Eres Tequendama, asesora digital de seguros para Latinoamérica (Colsubsidio), al estilo de Erica de Bank of America: cercana, resolutiva y experta. Respondes en el idioma del cliente (español por defecto). Tu misión es llevar al cliente de "no sé qué seguro necesito" a "ya quedé asegurada" en el mismo chat, sin humano.

CIERRE AUTÓNOMO (esto es lo que te diferencia):
- TÚ cierras la venta y emites la póliza aquí mismo. Colsubsidio DISTRIBUYE; la aseguradora EMITE; tú operas ese cierre. NUNCA digas que "un asesor licenciado cierra" ni derives el cierre a un humano por defecto.
- Sé eficiente: apunta a cerrar en ≤8 turnos. Flujo: descubrir (2-3 preguntas máx) → cotizar → que elija → capturar datos → consentimiento → pago → emitir → confirmar.

REGLAS DURAS:
- NUNCA des precios, primas ni coberturas de memoria: usa siempre `cotizar` o `buscar_productos`. Si no has llamado la herramienta, no hay cifra.
- Descubre conversando (1-2 preguntas por mensaje, nunca un interrogatorio): país, edad, necesidad (vida|salud|auto|hogar|viaje|pyme|accidentes|exequial|mascotas|movilidad), a quién protege, presupuesto mensual.
- Presenta máximo 3 opciones, con prima en moneda local primero y USD entre paréntesis, y 2-3 coberturas clave por opción en lenguaje simple.
- Cuando el cliente elija, ofrece cerrar de una vez. Puedes generar el PDF de la cotización con `generar_documento` si lo pide, pero el objetivo es EMITIR la póliza.

RECOLECCIÓN DE INFORMACIÓN REAL (para poder emitir de verdad):
- Cada seguro exige datos reales (identificación, SARLAFT/conocimiento del cliente, declaración de asegurabilidad/salud, datos del bien, beneficiarios). Usa `solicitar_informacion(insurance_type)` para saber QUÉ falta y pídelo de a poco, conversando (no un interrogatorio).
- Guarda cada dato que el cliente te dé con `guardar_datos_cliente({campo: valor})` usando los IDs del catálogo (ocupacion, ingresos_mensuales, fumador, preexistencias, placa, etc.).
- Si el cliente prefiere completar todo de una vez, usa `generar_formulario(insurance_type)` para enviarle un formulario estructurado.
- Si el cliente ENVÍA un archivo (cédula, tarjeta de propiedad, RUT, examen), usa `analizar_documento(file_id)` para leerlo y autocompletar datos; confírmale lo que extrajiste.
- Usa `perfilar_cliente` para entender su etapa de vida, riesgo, capacidad y necesidades, y personalizar la recomendación (ofrece lo que de verdad necesita).
- Pide solo lo mínimo necesario y sé transparente con por qué lo pides (SARLAFT, Habeas Data, declaración de asegurabilidad Art. 1058).

CÓMO CERRAR (usa las herramientas, en este orden):
1. `capturar_datos_cliente` — pide nombre completo y número de documento (CC), y de forma natural la fecha de nacimiento, email y ciudad. Completa además los datos obligatorios del producto (SARLAFT, salud/asegurabilidad, beneficiarios) con `guardar_datos_cliente`; consulta con `estado_kyc(insurance_type)` qué falta.
2. VALIDACIÓN DE IDENTIDAD Y DOCUMENTOS (OBLIGATORIA para emitir de verdad, esto da seguridad y evita fraude):
   a. Pídele la FOTO DE SU CÉDULA (frente). Cuando la envíe, súbela y regístrala con `registrar_documento_kyc(file_id, tipo="cedula_frente")` (o `analizar_documento(file_id, tipo="cedula_frente")` para además leer sus datos).
   b. Pídele una SELFIE (foto de su rostro, bien iluminada, de frente). Regístrala con `registrar_documento_kyc(file_id, tipo="selfie")`.
   c. Corre `verificar_identidad` — compara el rostro de la cédula con la selfie. Si es "aprobado", sigue; si "rechazado", pide una mejor selfie/cédula (máx. 2 intentos); si "no_disponible", avisa que un asesor validará la identidad. SIN identidad verificada NO emites.
   d. Pídele el DOCUMENTO FIRMADO de autorización/declaración de asegurabilidad (foto o PDF de la firma). Regístralo con `registrar_documento_kyc(file_id, tipo="autorizacion_firmada")`. En auto, pide también la tarjeta de propiedad (tipo="tarjeta_propiedad").
3. `registrar_consentimiento(acepta=true)` — OBLIGATORIO antes de emitir. Explica breve: "¿Autorizas el tratamiento de tus datos personales (Ley 1581/2012) para emitir la póliza?". Sin un "sí" explícito del cliente NO emites.
4. `evaluar_riesgo(insurance_type, monthly_premium_cop)` — underwriting OBLIGATORIO antes de cobrar. Si la decisión es AUTO_APPROVE sigue al pago; si es REFER, explica con calidez que un asesor revisa el caso y confirma en <24h (NO cobres ni emitas); si es DECLINE, sé honesto y ofrece una alternativa.
5. Pago: pregunta cómo prefiere pagar. Si elige tarjeta débito/crédito, usa `generar_link_pago(monto_cop)` con la prima mensual cotizada y entrégale el enlace: el pago ocurre en la página segura de la pasarela (Polar), en pesos colombianos. NUNCA pidas números de tarjeta, CVV ni claves en el chat. Cuando el cliente diga que ya pagó, confirma con `verificar_pago`; solo con estado APPROVED continúas. Si prefiere dejarlo simulado (o la pasarela no está disponible), usa payment_method="simulado".
6. `emitir_poliza(insurance_type, monthly_premium_cop, coverage, payment_method, payment_reference)` — emite la póliza real (con pago real pasa payment_method="tarjeta" y el payment_reference del pago aprobado). El sistema RECHAZA la emisión si faltan documentos, la identidad no está verificada o faltan datos obligatorios: si te devuelve `faltantes`, pídeselos al cliente y reintenta. Al recibir el número de póliza, CONFIRMA con calidez: "¡Ya quedaste asegurada! Tu póliza es N.º ...", entrega el enlace de descarga y menciona el derecho de retracto (5 días hábiles, Ley 1480/2011).

POSVENTA DE PAGOS: si el cliente reporta un cobro errado o duplicado, quiere el reembolso o ejerce su derecho de retracto, usa `solicitar_aclaracion(motivo)`: intenta la anulación en línea y, si no se puede, deja la aclaración registrada. Explícale el resultado y los tiempos con transparencia.

RENOVACIONES Y COMPLEMENTOS: si el cliente ya tiene una póliza (o te da su número POL-...), usa `proponer_renovacion(policy_number)` para ofrecerle la renovación con opciones frescas antes del vencimiento; la renovación se cierra con el mismo flujo (consentimiento → pago → emitir_poliza). Si `perfilar_cliente` muestra un vacío de protección evidente (ej. tiene auto y no vida), sugiérelo con tacto UNA sola vez, sin insistir.

SINIESTROS (el cliente reporta que le pasó algo): primero empatía — pregunta si está bien. Luego: (1) pide el número de póliza (POL-...) y qué pasó; (2) usa `reportar_siniestro(policy_number, descripcion, fecha_incidente, monto_estimado_cop, file_ids)` — si mandó fotos/documentos, pásalos en file_ids; (3) confírmale el número de reclamo CLM-..., explícale qué documentos faltan (`documentos_siniestro` si necesitas la lista) y que puede enviarlos por este mismo chat; (4) para seguimiento usa `estado_siniestro(claim_number)`. Las banderas de fraude del triage son INTERNAS del equipo: NUNCA las menciones al cliente.

INFORMES PERIÓDICOS: tras emitir la póliza (o si el cliente muestra interés continuo), ofrécele UNA vez recibir un informe por correo del estado de su seguro: "¿Te gustaría que te envíe un informe de tu seguro al correo? Puede ser semanal o mensual". Si acepta y te da el email, llama `suscribir_informes(email, frecuencia)`. Nunca lo suscribas sin su sí explícito.

DIVULGACIÓN (transparencia obligatoria antes de emitir): nombre de la aseguradora emisora, coberturas clave, exclusiones principales y la prima. No emitas si el cliente no vio la oferta.

LÍMITES:
- Pide los datos que la emisión real EXIGE (identificación, SARLAFT, declaración de asegurabilidad/salud según el producto, beneficiarios) explicando SIEMPRE por qué (Habeas Data Ley 1581/2012, reticencia Art. 1058). NUNCA pidas números de tarjeta, CVV ni contraseñas en el chat. No des consejo médico/legal/fiscal.
- Takeover humano SOLO si el cliente lo pide explícitamente: si lo pide, empatiza, llama `actualizar_lead` con la etapa actual y di que un asesor lo contactará. No es un paso obligatorio del cierre.
- Mensajes cortos tipo chat. Máximo un emoji por mensaje.

CONVERSACIÓN GUIADA: termina CADA respuesta con una última línea exacta:
SUGERENCIAS: opción 1 | opción 2 | opción 3
con 2-3 respuestas cortas que el cliente probablemente querría tocar (ej. "Sí, quiero contratar | Ver coberturas | Autorizo mis datos"). Esa línea no es parte del mensaje hablado."""


def _load_conocimiento() -> str:
    """Base de conocimiento del portafolio Colsubsidio (data/market)."""
    try:
        from .config import DATA_DIR
        return (DATA_DIR / "conocimiento_colsubsidio.md").read_text(encoding="utf-8").strip()
    except OSError:
        log.warning("sin conocimiento_colsubsidio.md; el agente opera solo con el catálogo")
        return ""


_CONOCIMIENTO_COLSUBSIDIO = _load_conocimiento()
if _CONOCIMIENTO_COLSUBSIDIO:
    SYSTEM_PROMPT_CLIENTE = f"{SYSTEM_PROMPT_CLIENTE}\n\n{_CONOCIMIENTO_COLSUBSIDIO}"

SYSTEM_PROMPT_GERENTE = """Eres Tequendama en modo analista para un GERENTE verificado del negocio de seguros. Estilo: analista de negocio senior, directo y accionable.

- Usa la herramienta `obtener_insights` para toda cifra (KPIs, funnel, países, productos, serie temporal). Nunca inventes datos.
- No vuelques JSON: responde la pregunta con 3-5 datos clave, una comparación relevante y UNA recomendación accionable.
- Tablas de texto simples para comparativas; números con separador de miles.
- Si pide seguimiento de leads usa `listar_leads`; si pide cambiar una etapa usa `actualizar_lead`.
- Termina cada respuesta con la línea:
SUGERENCIAS: pregunta 1 | pregunta 2
con 2 análisis de profundización que probablemente quiera (ej. "¿Dónde se caen los leads? | Compárame Colombia vs México")."""

TOOLS_SCHEMA = [
    {"type": "function", "function": {
        "name": "buscar_productos",
        "description": "Catálogo de productos de seguros disponibles, filtrable por país y tipo.",
        "parameters": {"type": "object", "properties": {
            "country": {"type": "string", "description": "Código ISO-2, ej. CO"},
            "tipo": {"type": "string", "enum": ["vida", "salud", "auto", "hogar", "viaje", "pyme", "accidentes", "exequial", "mascotas", "movilidad"]},
        }}}},
    {"type": "function", "function": {
        "name": "cotizar",
        "description": "Cotiza seguros a la medida y devuelve hasta 3 opciones con quote_id, prima en moneda local y USD, y coberturas. Única fuente válida de precios.",
        "parameters": {"type": "object", "required": ["country"], "properties": {
            "country": {"type": "string", "description": "Código ISO-2 del país"},
            "tipo": {"type": "string", "enum": ["vida", "salud", "auto", "hogar", "viaje", "pyme", "accidentes", "exequial", "mascotas", "movilidad"]},
            "age": {"type": "integer"},
            "name": {"type": "string", "description": "Nombre del cliente si lo dio"},
            "budget_monthly_usd": {"type": "number"},
            "sum_assured_usd": {"type": "number"},
            "extras": {"type": "object", "description": "afiliado_colsubsidio (true si es afiliado: tarifa preferencial), fumador, dependientes, valor_bien_usd, dias_viaje, zona_alto_riesgo, preexistencias, destino_usa_europa...",
                       "properties": {}, "additionalProperties": True},
        }}}},
    {"type": "function", "function": {
        "name": "generar_documento",
        "description": "Genera la cotización formal en PDF de una opción ya cotizada. Devuelve la URL de descarga.",
        "parameters": {"type": "object", "required": ["quote_id"], "properties": {
            "quote_id": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "actualizar_lead",
        "description": "Actualiza los datos o la etapa del funnel del cliente (nuevo|descubrimiento|cotizado|documento|cerrado|perdido).",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}, "country": {"type": "string"},
            "age": {"type": "integer"},
            "stage": {"type": "string", "enum": ["nuevo", "descubrimiento", "cotizado", "documento", "cerrado", "perdido"]},
        }}}},
    {"type": "function", "function": {
        "name": "capturar_datos_cliente",
        "description": "Guarda en la sesión los datos del cliente necesarios para emitir la póliza. Llámala cuando el cliente decida contratar. Devuelve qué campos aún faltan.",
        "parameters": {"type": "object", "required": ["fullName", "document_id"], "properties": {
            "fullName": {"type": "string", "description": "Nombre completo del cliente"},
            "document_id": {"type": "string", "description": "Número de documento (CC). Obligatorio, no vacío"},
            "document_type": {"type": "string", "description": "Tipo de documento", "default": "CC"},
            "birth_date": {"type": "string", "description": "Fecha de nacimiento AAAA-MM-DD (opcional)"},
            "email": {"type": "string", "description": "Correo (opcional)"},
            "city": {"type": "string", "description": "Ciudad (opcional)"},
        }}}},
    {"type": "function", "function": {
        "name": "registrar_consentimiento",
        "description": "Registra el consentimiento de habeas data (Ley 1581/2012). OBLIGATORIO antes de emitir. Sin acepta=true no se puede emitir la póliza.",
        "parameters": {"type": "object", "required": ["acepta"], "properties": {
            "acepta": {"type": "boolean", "description": "true si el cliente autorizó explícitamente el tratamiento de sus datos"}}}}},
    {"type": "function", "function": {
        "name": "evaluar_riesgo",
        "description": "Underwriting semiautónomo: evalúa si la póliza elegida puede emitirse automáticamente. OBLIGATORIO después del consentimiento y ANTES de cobrar/emitir. AUTO_APPROVE = continúa con pago y emisión; REFER = un gerente debe aprobar (NO cobres ni emitas: explica que un asesor confirma en <24h); DECLINE = no asegurable por este canal, ofrece alternativas.",
        "parameters": {"type": "object", "required": ["insurance_type", "monthly_premium_cop"], "properties": {
            "insurance_type": {"type": "string", "description": "Tipo de seguro elegido (vida|salud|auto|hogar|viaje|pyme|accidentes)"},
            "monthly_premium_cop": {"type": "number", "description": "Prima mensual en COP de la opción elegida"},
        }}}},
    {"type": "function", "function": {
        "name": "emitir_poliza",
        "description": "Emite la póliza REAL vía el backend (crea Customer->Lead->Quote->Policy) y genera el PDF/certificado. Requiere datos capturados + consentimiento=true; con payment_method distinto de 'simulado' exige además un pago APPROVED (verificar_pago). Devuelve el número de póliza y el enlace de descarga.",
        "parameters": {"type": "object", "required": ["insurance_type", "monthly_premium_cop"], "properties": {
            "insurance_type": {"type": "string", "description": "Tipo de seguro elegido (vida|salud|auto|hogar|viaje|pyme|accidentes)"},
            "monthly_premium_cop": {"type": "number", "description": "Prima mensual en COP de la opción elegida"},
            "coverage": {"type": "object", "description": "Resumen de la oferta: {aseguradora, coberturas:[...], resumen}",
                         "properties": {}, "additionalProperties": True},
            "payment_method": {"type": "string", "description": "Método de pago: 'tarjeta' si pagó con el link real, 'simulado' para el demo", "default": "simulado"},
            "payment_reference": {"type": "string", "description": "Referencia SEG-... del pago aprobado (obligatoria si payment_method no es 'simulado')"},
        }}}},
    {"type": "function", "function": {
        "name": "generar_link_pago",
        "description": "Genera el link de pago REAL (Polar: tarjeta débito/crédito, cobro en COP) por la prima de la póliza y devuelve reference + checkout_url para entregar al cliente. El pago ocurre en la página segura de la pasarela: NUNCA pidas datos de tarjeta en el chat.",
        "parameters": {"type": "object", "required": ["monto_cop"], "properties": {
            "monto_cop": {"type": "number", "description": "Monto a cobrar en COP (normalmente la prima mensual de la opción elegida)"},
            "descripcion": {"type": "string", "description": "Concepto del cobro, ej. 'Primera mensualidad — Seguro de Vida'"},
        }}}},
    {"type": "function", "function": {
        "name": "verificar_pago",
        "description": "Consulta el estado real del pago (webhook del backend + API de Polar). Úsala cuando el cliente diga que ya pagó y SIEMPRE antes de emitir_poliza con método distinto de 'simulado'. Solo APPROVED permite emitir.",
        "parameters": {"type": "object", "properties": {
            "reference": {"type": "string", "description": "Referencia SEG-... (opcional: por defecto el último pago de la sesión)"},
            "transaction_id": {"type": "string", "description": "ID de la orden de Polar del comprobante, si el cliente lo tiene"},
        }}}},
    {"type": "function", "function": {
        "name": "solicitar_aclaracion",
        "description": "Aclaración/disputa de un pago ya realizado: intenta el reembolso total de la orden en línea y, si no es posible, registra la aclaración para gestión con la pasarela. Úsala ante cobros errados/duplicados o derecho de retracto.",
        "parameters": {"type": "object", "required": ["motivo"], "properties": {
            "motivo": {"type": "string", "description": "Motivo del cliente, ej. 'cobro duplicado', 'derecho de retracto'"},
            "reference": {"type": "string", "description": "Referencia SEG-... del pago (opcional: por defecto el último de la sesión)"},
        }}}},
    {"type": "function", "function": {
        "name": "obtener_insights",
        "description": "SOLO GERENTES: KPIs, funnel, ventas por país y producto, serie temporal.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "listar_leads",
        "description": "SOLO GERENTES: últimos leads con cotizaciones y prima.",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "default": 20}}}}},
    {"type": "function", "function": {
        "name": "solicitar_informacion",
        "description": "Consulta qué información REAL falta para emitir un seguro (KYC/SARLAFT/declaración de asegurabilidad por producto). Devuelve % de avance y los próximos campos a pedir. Úsala antes de emitir para saber qué preguntar.",
        "parameters": {"type": "object", "required": ["insurance_type"], "properties": {
            "insurance_type": {"type": "string", "description": "vida|salud|auto|hogar|viaje|pyme|accidentes"}}}}},
    {"type": "function", "function": {
        "name": "guardar_datos_cliente",
        "description": "Guarda uno o varios campos de información del cliente recolectados en la conversación (ej. ocupacion, ingresos_mensuales, fumador, placa, preexistencias...). Usa los IDs de campo del catálogo.",
        "parameters": {"type": "object", "required": ["campos"], "properties": {
            "campos": {"type": "object", "description": "dict {id_campo: valor} — ej. {\"ocupacion\":\"ingeniera\",\"fumador\":\"no\",\"placa\":\"ABC123\"}",
                       "properties": {}, "additionalProperties": True}}}}},
    {"type": "function", "function": {
        "name": "generar_formulario",
        "description": "Genera un formulario estructurado (por secciones) con TODOS los datos que se necesitan para un seguro, para enviárselo al cliente y que lo complete de una vez en vez de pregunta por pregunta.",
        "parameters": {"type": "object", "required": ["insurance_type"], "properties": {
            "insurance_type": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "analizar_documento",
        "description": "Lee un archivo que el cliente envió (cédula, tarjeta de propiedad, RUT, examen...) y extrae datos para autocompletar el intake. Si es un documento KYC del cierre, pasa `tipo` (cedula_frente|cedula_reverso|selfie|autorizacion_firmada|tarjeta_propiedad) para que quede registrado como documento del expediente.",
        "parameters": {"type": "object", "required": ["file_id"], "properties": {
            "file_id": {"type": "string"},
            "tipo": {"type": "string", "description": "Tipo de documento KYC si aplica",
                     "enum": ["cedula_frente", "cedula_reverso", "selfie", "autorizacion_firmada", "tarjeta_propiedad", "comprobante_pago", "otro"]}}}}},
    {"type": "function", "function": {
        "name": "registrar_documento_kyc",
        "description": "Registra en el expediente del cliente un archivo que ya subió (por su file_id) como documento KYC de un tipo concreto (cédula, selfie, autorización firmada...). Necesario para poder emitir. Devuelve el estado del expediente.",
        "parameters": {"type": "object", "required": ["file_id", "tipo"], "properties": {
            "file_id": {"type": "string", "description": "file_id que devolvió la subida del archivo"},
            "tipo": {"type": "string", "enum": ["cedula_frente", "cedula_reverso", "selfie", "autorizacion_firmada", "tarjeta_propiedad", "comprobante_pago", "otro"]}}}}},
    {"type": "function", "function": {
        "name": "verificar_identidad",
        "description": "Verificación biométrica: compara el rostro de la foto de la cédula (cedula_frente) con la selfie del cliente (ambas ya registradas con registrar_documento_kyc). OBLIGATORIA antes de emitir. Devuelve aprobado|rechazado|revision|no_disponible con un puntaje de coincidencia. Si rechaza, pide una selfie mejor; si es no_disponible, avísale que un asesor validará la identidad.",
        "parameters": {"type": "object", "properties": {
            "doc_file_id": {"type": "string", "description": "opcional: file_id de la cédula (por defecto usa el registrado)"},
            "selfie_file_id": {"type": "string", "description": "opcional: file_id de la selfie (por defecto usa la registrada)"}}}}},
    {"type": "function", "function": {
        "name": "estado_kyc",
        "description": "Estado del expediente del cliente para cerrar: qué datos obligatorios faltan, qué documentos faltan/recibidos, si la identidad está verificada y si hay consentimiento. Úsalo para saber exactamente qué pedir a continuación y antes de intentar emitir.",
        "parameters": {"type": "object", "properties": {
            "insurance_type": {"type": "string", "description": "vida|salud|auto|hogar|viaje|pyme|accidentes"}}}}},
    {"type": "function", "function": {
        "name": "perfilar_cliente",
        "description": "Hiper-perfilamiento: analiza los datos recolectados y devuelve etapa de vida, segmento de riesgo, capacidad de pago, necesidades detectadas, productos recomendados, propensión y banderas. Úsalo para personalizar la recomendación.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "reportar_siniestro",
        "description": "FNOL: registra el primer aviso de siniestro de una póliza VIGENTE. Valida la póliza, hace el triage y devuelve el número de reclamo (CLM-...) y los documentos requeridos. Si el cliente adjuntó fotos/documentos, pasa sus file_ids.",
        "parameters": {"type": "object", "required": ["policy_number", "descripcion"], "properties": {
            "policy_number": {"type": "string", "description": "Número de póliza, ej. POL-2026-000123"},
            "descripcion": {"type": "string", "description": "Qué pasó, en palabras del cliente"},
            "fecha_incidente": {"type": "string", "description": "Fecha del incidente AAAA-MM-DD (si la dio)"},
            "monto_estimado_cop": {"type": "number", "description": "Pérdida estimada en COP (si la dio)"},
            "file_ids": {"type": "array", "items": {"type": "string"},
                         "description": "file_ids de documentos/fotos que el cliente subió al chat"},
        }}}},
    {"type": "function", "function": {
        "name": "estado_siniestro",
        "description": "Consulta el estado actual de un reclamo por su número CLM-... (reportado|en_revision|docs_pendientes|aprobado|rechazado|pagado).",
        "parameters": {"type": "object", "required": ["claim_number"], "properties": {
            "claim_number": {"type": "string", "description": "Número de reclamo, ej. CLM-2026-000001"}}}}},
    {"type": "function", "function": {
        "name": "documentos_siniestro",
        "description": "Lista los documentos de soporte que exige un tipo de siniestro (auto|vida|salud|hogar|viaje|accidentes|pyme), para decirle al cliente qué debe enviar.",
        "parameters": {"type": "object", "required": ["tipo"], "properties": {
            "tipo": {"type": "string", "description": "Tipo de seguro del siniestro"}}}}},
    {"type": "function", "function": {
        "name": "proponer_renovacion",
        "description": "Renovación de una póliza emitida: consulta la póliza por su número, calcula cuánto falta para el vencimiento y cotiza opciones frescas del mismo tipo (con el perfil del cliente). Úsala cuando el cliente quiera renovar o cuando su póliza esté por vencer.",
        "parameters": {"type": "object", "required": ["policy_number"], "properties": {
            "policy_number": {"type": "string", "description": "Número de póliza, ej. POL-2026-000123"}}}}},
    {"type": "function", "function": {
        "name": "suscribir_informes",
        "description": "Suscribe al cliente a informes periódicos por correo sobre el estado de su seguro (cotizaciones, póliza, recomendaciones). Úsala SOLO cuando el cliente acepte explícitamente recibirlos y haya dado su email. Frecuencias: semanal | mensual (también diaria si la pide).",
        "parameters": {"type": "object", "required": ["email", "frecuencia"], "properties": {
            "email": {"type": "string", "description": "Correo del cliente"},
            "frecuencia": {"type": "string", "enum": ["diaria", "semanal", "mensual"]},
        }}}},
]


# ---------- Store de sesión de cierre (checkout) ----------

CHECKOUT_REQUIRED = ("full_name", "document_id")  # mínimos para emitir


def _checkout_table(conn: psycopg.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS checkout_session (
        session_key TEXT PRIMARY KEY,
        full_name TEXT,
        document_type TEXT DEFAULT 'CC',
        document_id TEXT,
        birth_date TEXT,
        email TEXT,
        phone TEXT,
        city TEXT,
        department TEXT,
        consent INTEGER DEFAULT 0,
        consent_at TEXT,
        updated_at TIMESTAMPTZ DEFAULT now())""")


def _get_checkout(conn: psycopg.Connection, key: str) -> dict:
    _checkout_table(conn)
    row = conn.execute("SELECT * FROM checkout_session WHERE session_key=%s", (key,)).fetchone()
    return dict(row) if row else {}


def _save_checkout(conn: psycopg.Connection, key: str, **fields) -> dict:
    """Upsert de los campos no nulos del cliente/consentimiento en la sesión."""
    _checkout_table(conn)
    current = _get_checkout(conn, key)
    merged = {**current}
    for k, v in fields.items():
        if v is not None:
            merged[k] = v
    cols = ("full_name", "document_type", "document_id", "birth_date", "email",
            "phone", "city", "department", "consent", "consent_at")
    if current:
        sets = ", ".join(f"{c}=%s" for c in cols) + ", updated_at=now()"
        conn.execute(f"UPDATE checkout_session SET {sets} WHERE session_key=%s",
                     (*[merged.get(c) for c in cols], key))
    else:
        conn.execute(
            f"INSERT INTO checkout_session (session_key, {', '.join(cols)}) "
            f"VALUES (%s{',%s' * len(cols)})",
            (key, *[merged.get(c) for c in cols]))
    conn.commit()
    return _get_checkout(conn, key)


# --- Store flexible (JSON) para el intake completo: todos los campos del catálogo ---

def _intake_table(conn: psycopg.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS intake_session (
        session_key TEXT PRIMARY KEY, datos TEXT DEFAULT '{}',
        updated_at TIMESTAMPTZ DEFAULT now())""")


def _get_intake(conn: psycopg.Connection, key: str) -> dict:
    _intake_table(conn)
    row = conn.execute("SELECT datos FROM intake_session WHERE session_key=%s", (key,)).fetchone()
    try:
        return json.loads(row["datos"]) if row and row["datos"] else {}
    except (json.JSONDecodeError, TypeError):
        return {}


# IDs del catálogo que además alimentan la emisión (checkout_session).
_INTAKE_TO_CHECKOUT = {
    "nombre_completo": "full_name", "tipo_documento": "document_type",
    "numero_documento": "document_id", "fecha_nacimiento": "birth_date",
    "email": "email", "telefono": "phone", "ciudad": "city",
    "departamento": "department",
}


def _save_intake(conn: psycopg.Connection, key: str, campos: dict) -> dict:
    """Mezcla campos en el store JSON y refleja los clave en checkout_session."""
    _intake_table(conn)
    datos = _get_intake(conn, key)
    datos.update({k: v for k, v in campos.items() if v is not None})
    conn.execute(
        "INSERT INTO intake_session (session_key, datos, updated_at) VALUES (%s,%s,now()) "
        "ON CONFLICT(session_key) DO UPDATE SET datos=excluded.datos, updated_at=now()",
        (key, json.dumps(datos, ensure_ascii=False)))
    conn.commit()
    # refleja identidad/contacto hacia el checkout para poder emitir
    mirror = {dst: campos[src] for src, dst in _INTAKE_TO_CHECKOUT.items() if src in campos}
    if mirror:
        _save_checkout(conn, key, **mirror)
    return datos


def _checkout_missing(sess: dict) -> list[str]:
    """Campos mínimos que aún faltan para poder emitir."""
    labels = {"full_name": "nombre completo", "document_id": "número de documento"}
    return [labels[f] for f in CHECKOUT_REQUIRED if not (sess.get(f) or "").strip()]


def _session_profile(conn: psycopg.Connection, session_key: str) -> dict | None:
    """Perfil determinista del cliente a partir del intake + checkout de la sesión."""
    try:
        from . import profiling
        datos = {**_get_intake(conn, session_key), **_get_checkout(conn, session_key)}
        return profiling.build_profile(datos) if datos else None
    except Exception:
        log.debug("perfil de sesión no disponible", exc_info=True)
        return None


_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)


def _notify_referral(tenant_id: str, uw: dict, sess: dict) -> None:
    """Crea la alerta de suscripción humana en el panel gerencial (best-effort).

    El gerente ve el caso en AlertsPanel y lo aprueba/emite manualmente; un
    fallo del backend nunca rompe el turno del agente."""
    try:
        import requests
        nombre = sess.get("full_name") or "Cliente del chat"
        msg = (f"Underwriting: {nombre} — seguro de {uw.get('tipo', '').lower()} por "
               f"{uw.get('prima_cop', 0):,.0f} COP/mes requiere aprobación humana. "
               f"Motivos: {'; '.join(uw.get('reasons', []))}")
        payload = {"message": msg[:900], "severity": "alta"}
        # El DTO exige UUID v4; el tenant demo no lo es → alerta global.
        if _UUID4_RE.match(tenant_id or ""):
            payload["teamId"] = tenant_id
        requests.post(f"{BACKEND_URL}/api/v1/alerts", json=payload, timeout=5,
                      headers={"X-Tenant-Id": tenant_id})
    except Exception:
        log.debug("no se pudo crear la alerta de referral", exc_info=True)


def _emitir_poliza(conn: psycopg.Connection, args: dict, *, phone: str,
                   tenant_id: str) -> dict:
    """Cierra la venta: valida sesión + consentimiento, llama al backend NestJS
    (`POST {BACKEND_URL}/api/v1/checkout`) reenviando `X-Tenant-Id`, genera el PDF
    de la póliza y devuelve `{policyNumber, download_url, ...}`. Degrada limpio si
    el backend no responde. La sesión de cierre está particionada por `(tenant_id, user_id)`."""
    session_key = f"{tenant_id}:{phone}"
    sess = _get_checkout(conn, session_key)
    faltan = _checkout_missing(sess)
    if faltan:
        return {"error": "faltan datos del cliente para emitir: " + ", ".join(faltan),
                "faltan": faltan, "necesita": "capturar_datos_cliente"}
    if not sess.get("consent"):
        return {"error": "falta el consentimiento de habeas data (Ley 1581/2012); "
                         "regístralo con registrar_consentimiento antes de emitir",
                "necesita": "registrar_consentimiento"}

    insurance_type = (str(args.get("insurance_type") or "").strip().upper() or "VIDA")

    # Gate KYC/identidad (anti-fraude): sin los documentos esenciales + la identidad
    # verificada (biometría cédula↔selfie) + los datos obligatorios NO se emite.
    # Configurable con KYC_ENFORCE (default true). El consentimiento y el pago se
    # validan aparte (arriba y abajo).
    from . import kyc
    from .config import KYC_ENFORCE
    gate = kyc.gate(conn, session_key, insurance_type)
    if not gate["ok"] and KYC_ENFORCE:
        return {"error": "no se puede emitir todavía: faltan requisitos de cumplimiento — "
                         + "; ".join(gate["faltantes"]),
                "faltan_kyc": gate["faltantes"], "necesita": "completar_kyc",
                "documentos_ok": gate["documentos_ok"], "identidad_ok": gate["identidad_ok"],
                "datos_ok": gate["datos_ok"],
                "mensaje": ("Pide al cliente lo que falta (foto de cédula, selfie para verificar "
                            "identidad, documento firmado y datos obligatorios) y reintenta emitir.")}

    try:
        prima = round(float(args.get("monthly_premium_cop") or 0), 2)
    except (ValueError, TypeError):
        prima = 0.0
    coverage = args.get("coverage") if isinstance(args.get("coverage"), dict) else {}
    payment_method = (args.get("payment_method") or "simulado").strip().lower()
    payment_reference = (args.get("payment_reference") or "").strip() or None

    # Con pago real, la póliza solo se emite contra un pago APPROVED (el estado
    # lo mantienen el webhook de Polar y verificar_pago; misma filosofía que el
    # consentimiento: sin herramienta no hay emisión).
    if payment_method not in ("simulado", "demo"):
        from . import payments
        pago = payments.approved_for_session(conn, session_key,
                                             reference=payment_reference)
        if not pago:
            return {"error": "el pago aún no está aprobado; genera el link con "
                             "generar_link_pago, espera a que el cliente pague y "
                             "confirma con verificar_pago antes de emitir",
                    "necesita": "verificar_pago"}
        payment_reference = pago["reference"]

    # Underwriting (red de seguridad): sin AUTO_APPROVE no hay emisión autónoma.
    # El flujo normal ya pasó por `evaluar_riesgo`; esto cubre al modelo si lo salta.
    from . import underwriting
    uw = underwriting.evaluate(_session_profile(conn, session_key),
                               insurance_type=insurance_type,
                               monthly_premium_cop=prima)
    if uw["decision"] == underwriting.REFER:
        _notify_referral(tenant_id, uw, sess)
        return {"underwriting": uw, "referred": True,
                "error": "la solicitud requiere aprobación de un gerente antes de emitir",
                "mensaje": ("Explica al cliente con calidez que su caso pasó a revisión de un "
                            "asesor y que le confirman en menos de 24 horas. Si ya pagó, "
                            "aclárale que el pago queda registrado y se aplica (o reembolsa) "
                            "con la decisión.")}
    if uw["decision"] == underwriting.DECLINE:
        return {"underwriting": uw, "referred": False,
                "error": "no es posible emitir esta póliza por este canal",
                "mensaje": "Sé honesto con el motivo y ofrece alternativas de protección."}
    # Decisión auditable: viaja en Quote.coverage.underwriting vía el checkout.
    coverage = {**(coverage or {}),
                "underwriting": {k: uw[k] for k in
                                 ("decision", "reasons", "segmento_riesgo",
                                  "umbral_autoemision_cop")}}
    coverage.setdefault("resumen", f"Seguro de {insurance_type.lower()}")

    real_phone = sess.get("phone") or (phone if phone and not phone.startswith("web:") else None)
    customer = {
        "fullName": sess.get("full_name"),
        "documentType": sess.get("document_type") or "CC",
        "documentId": sess.get("document_id"),
        "birthDate": sess.get("birth_date"),
        "email": sess.get("email"),
        "phone": real_phone,
        "city": sess.get("city"),
        "department": sess.get("department"),
    }
    customer = {k: v for k, v in customer.items() if v}  # el upsert tolera opcionales ausentes

    payload = {
        "customer": customer,
        "consentData": True,
        "insuranceType": insurance_type,
        "monthlyPremiumCop": prima,
        "coverage": coverage or {"resumen": f"Seguro de {insurance_type.lower()}"},
        "payment": {"method": payment_method, "reference": payment_reference or "demo"},
        "leadId": None,
    }

    degraded = False
    note = ""
    policy: dict
    try:
        import requests
        # Reenvía el tenant para que el backend cree la cadena Customer->...->Policy
        # bajo el Team correcto (partición dura de dos ejes, patrón Paloma).
        resp = requests.post(f"{BACKEND_URL}/api/v1/checkout", json=payload, timeout=8,
                             headers={"X-Tenant-Id": tenant_id})
        resp.raise_for_status()
        policy = resp.json() or {}
        log.info("póliza emitida por el backend: %s", policy.get("policyNumber"))
    except Exception as exc:  # backend caído/timeout/no-2xx: no crashea, degrada
        log.warning("checkout backend no disponible (%s); emisión provisional local", exc)
        degraded = True
        note = ("El sistema central de emisión no respondió; se generó una confirmación "
                "provisional. Quedará en firme cuando el backend vuelva a estar disponible.")
        from datetime import datetime as _dt, timedelta as _td
        now = _dt.utcnow()
        policy = {
            "policyNumber": f"POL-LOCAL-{now.strftime('%Y')}-{now.strftime('%m%d%H%M%S')}",
            "policyId": None, "customerId": None, "status": "provisional",
            "startDate": now.isoformat(timespec="seconds"),
            "endDate": (now + _td(days=365)).isoformat(timespec="seconds"),
            "insuranceType": insurance_type, "monthlyPremiumCop": prima,
        }

    # Certificado/carátula PDF de la póliza
    download_url = None
    try:
        policy_for_pdf = {**policy, "aseguradora": coverage.get("aseguradora")}
        path = build_policy_pdf(policy_for_pdf, customer, coverage)
        from pathlib import Path
        download_url = f"/api/documents/{Path(path).name}"
    except Exception:  # el PDF no debe tumbar la emisión
        log.exception("no se pudo generar el PDF de la póliza")

    # Marca el lead como cerrado localmente (best-effort, para el panel gerencial)
    try:
        if phone:
            conn.execute("UPDATE leads SET stage='cerrado', updated_at=now() "
                         "WHERE phone=%s AND stage NOT IN ('cerrado','perdido')", (phone,))
            conn.commit()
    except Exception:
        log.debug("no se pudo actualizar el lead a cerrado", exc_info=True)

    out = {
        "policyNumber": policy.get("policyNumber"),
        "policyId": policy.get("policyId"),
        "status": policy.get("status"),
        "startDate": policy.get("startDate"),
        "endDate": policy.get("endDate"),
        "insurance_type": insurance_type,
        "monthly_premium_cop": prima,
        "download_url": download_url,
        "degraded": degraded,
        "mensaje": ("Póliza emitida. Confirma al cliente 'ya quedaste asegurada', entrega el "
                    "enlace de descarga e informa el derecho de retracto (5 días hábiles)."),
    }
    if note:
        out["nota"] = note
    return out


def _exec_tool(name: str, args: dict, *, phone: str, role: str,
               tenant_id: str = "demo") -> Any:
    """Ejecuta una herramienta contra la lógica local (payload estructurado, validado).

    `tenant_id` y `phone` (user_id) viajan SIEMPRE como argumentos (patrón Paloma:
    nunca en estado del módulo). La sesión de cierre/intake se particiona por el par
    `(tenant_id, user_id)` vía `session_key`."""
    conn = get_conn()
    session_key = f"{tenant_id}:{phone}"  # partición dura de sesión (tenant_id, user_id)
    try:
        if name == "buscar_productos":
            rows = conn.execute("SELECT * FROM products").fetchall()
            out = []
            for r in rows:
                paises = json.loads(r["paises"])
                if args.get("country") and args["country"].upper() not in paises:
                    continue
                if args.get("tipo") and r["tipo"] != args["tipo"]:
                    continue
                out.append({"id": r["id"], "tipo": r["tipo"], "nombre": r["nombre"],
                            "aseguradora": r["aseguradora"],
                            "coberturas": json.loads(r["coberturas"])})
            return out or {"aviso": "sin productos con ese filtro; sugiere el tipo más cercano"}

        if name == "cotizar":
            if not args.get("country"):
                return {"error": "falta el país (country); pregúntaselo al cliente"}
            country = str(args["country"]).upper()
            if country not in COUNTRY_NAMES:
                return {"error": f"país no soportado: {country}", "soportados": list(COUNTRY_NAMES)}
            # Pricing personalizado: el perfil (intake + checkout de la sesión)
            # ajusta la prima de forma acotada y explicable en el breakdown.
            perfil = None
            try:
                from . import profiling
                datos = {**_get_intake(conn, session_key), **_get_checkout(conn, session_key)}
                if args.get("age") is not None:
                    datos.setdefault("edad", args["age"])
                for k, v in (args.get("extras") or {}).items():
                    datos.setdefault(k, v)
                if datos:
                    perfil = profiling.build_profile(datos)
            except Exception:
                log.debug("perfil no disponible para cotizar", exc_info=True)
            options = recommend(conn, country=country, tipo=args.get("tipo"),
                                age=args.get("age"), sum_assured_usd=args.get("sum_assured_usd"),
                                budget_monthly_usd=args.get("budget_monthly_usd"),
                                extras=args.get("extras") or {}, perfil=perfil)
            ajuste_perfil = next((o["breakdown"].get("ajuste_perfil_riesgo")
                                  for o in options
                                  if o.get("breakdown", {}).get("ajuste_perfil_riesgo")), None)
            from .main import _upsert_lead  # reusa el upsert canónico
            lead_id = _upsert_lead(conn, phone, args.get("name"), country, args.get("age"),
                                   stage="cotizado" if options else "descubrimiento")
            for o in options:
                o["quote_id"] = conn.execute(
                    """INSERT INTO quotes (lead_id, product_id, country, currency, sum_assured_usd,
                       premium_monthly_usd, premium_monthly_local, breakdown)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (lead_id, o["product_id"], country, o["moneda"], o["suma_asegurada_usd"],
                     o["prima_mensual_usd"], o["prima_mensual_local"],
                     json.dumps(o["breakdown"], ensure_ascii=False))).fetchone()["id"]
                o.pop("breakdown", None)
            conn.commit()
            out_cotizar: dict[str, Any] = {"opciones": options}
            if ajuste_perfil:
                out_cotizar["precio_personalizado"] = {
                    **ajuste_perfil,
                    "explicacion": ("La prima está ajustada al perfil de riesgo del cliente "
                                    f"(segmento {ajuste_perfil['segmento']}). Explícaselo con "
                                    "transparencia: su precio refleja su riesgo real, no un promedio."),
                }
            return out_cotizar

        if name == "generar_documento":
            if not args.get("quote_id"):
                return {"error": "falta quote_id; cotiza primero y usa el quote_id de la opción elegida"}
            q = conn.execute(
                """SELECT q.*, p.nombre producto, p.tipo, p.aseguradora, p.coberturas, p.prima_por_dia
                   FROM quotes q JOIN products p ON p.id=q.product_id WHERE q.id=%s""",
                (args["quote_id"],)).fetchone()
            if not q:
                return {"error": "quote_id no existe; cotiza primero"}
            lead = dict(conn.execute("SELECT * FROM leads WHERE id=%s", (q["lead_id"],)).fetchone() or {}) if q["lead_id"] else None
            quote_dict = {
                "product_id": q["product_id"], "producto": q["producto"], "tipo": q["tipo"],
                "aseguradora": q["aseguradora"], "pais": COUNTRY_NAMES.get(q["country"], q["country"]),
                "moneda": q["currency"], "suma_asegurada_usd": q["sum_assured_usd"],
                "prima_mensual_usd": q["premium_monthly_usd"],
                "prima_mensual_local": q["premium_monthly_local"],
                "tasa_fx": (q["premium_monthly_local"] / q["premium_monthly_usd"]) if q["premium_monthly_usd"] else 1.0,
                "coberturas": json.loads(q["coberturas"]),
                "periodicidad": "por viaje" if q["prima_por_dia"] else "mensual",
            }
            path = build_quote_pdf(quote_dict, lead)
            conn.execute("UPDATE quotes SET status='documento' WHERE id=%s", (args["quote_id"],))
            if q["lead_id"]:
                conn.execute("UPDATE leads SET stage='documento', updated_at=now() "
                             "WHERE id=%s AND stage NOT IN ('cerrado','perdido')", (q["lead_id"],))
            conn.commit()
            from pathlib import Path
            return {"download_url": f"/api/documents/{Path(path).name}",
                    "mensaje": "documento generado; entrega este enlace al cliente"}

        if name == "actualizar_lead":
            from .main import _upsert_lead
            lead_id = _upsert_lead(conn, phone, args.get("name"),
                                   (args.get("country") or "CO").upper(), args.get("age"),
                                   args.get("stage") or "descubrimiento")
            conn.commit()
            return {"ok": True, "lead_id": lead_id}

        if name == "capturar_datos_cliente":
            document_id = str(args.get("document_id") or "").strip()
            full_name = str(args.get("fullName") or args.get("full_name") or "").strip()
            # phone real si el session_key es un teléfono (no 'web:...')
            real_phone = phone if phone and not phone.startswith("web:") else None
            sess = _save_checkout(
                conn, session_key,
                full_name=full_name or None,
                document_id=document_id or None,
                document_type=args.get("document_type") or "CC",
                birth_date=args.get("birth_date"),
                email=args.get("email"),
                city=args.get("city"),
                phone=real_phone)
            faltan = _checkout_missing(sess)
            if not document_id:
                return {"error": "el número de documento es obligatorio y no puede ir vacío",
                        "faltan": faltan or ["número de documento"], "guardado": bool(sess)}
            deseables = [lbl for f, lbl in (("email", "email"), ("city", "ciudad"),
                                            ("birth_date", "fecha de nacimiento"))
                         if not (sess.get(f) or "").strip()]
            return {"ok": True, "faltan": faltan, "opcionales_faltantes": deseables,
                    "consentimiento": bool(sess.get("consent")),
                    "mensaje": ("Datos capturados. Falta: " + ", ".join(faltan)) if faltan
                    else "Datos completos para emitir."}

        if name == "registrar_consentimiento":
            acepta = bool(args.get("acepta"))
            if not acepta:
                return {"error": "el cliente no autorizó el tratamiento de datos; "
                                 "sin consentimiento no se puede emitir la póliza",
                        "consentimiento": False}
            from datetime import datetime as _dt
            _save_checkout(conn, session_key, consent=1, consent_at=_dt.utcnow().isoformat())
            return {"ok": True, "consentimiento": True,
                    "mensaje": "Consentimiento de habeas data registrado."}

        if name == "evaluar_riesgo":
            from . import underwriting
            uw = underwriting.evaluate(
                _session_profile(conn, session_key),
                insurance_type=str(args.get("insurance_type") or ""),
                monthly_premium_cop=args.get("monthly_premium_cop") or 0)
            if uw["decision"] == underwriting.REFER:
                _notify_referral(tenant_id, uw, _get_checkout(conn, session_key))
                uw["mensaje"] = ("Caso escalado a un gerente (ya tiene la alerta en su panel). "
                                 "Explícale al cliente con calidez que un asesor revisa su "
                                 "solicitud y le confirma en menos de 24 horas. NO generes "
                                 "link de pago ni emitas.")
            elif uw["decision"] == underwriting.DECLINE:
                uw["mensaje"] = ("No se puede emitir por este canal. Sé honesto con el motivo "
                                 "y ofrece una alternativa de protección.")
            else:
                uw["mensaje"] = "Aprobación automática. Continúa con el pago y la emisión."
            return uw

        if name == "emitir_poliza":
            return _emitir_poliza(conn, args, phone=phone, tenant_id=tenant_id)

        # ---------- Reclamos (FNOL) ----------
        if name == "reportar_siniestro":
            from . import claims_ai
            return claims_ai.reportar_siniestro(conn, tenant_id, args)

        if name == "estado_siniestro":
            from . import claims_ai
            return claims_ai.estado_siniestro(conn, args)

        if name == "documentos_siniestro":
            from . import claims_ai
            tipo = str(args.get("tipo") or "").lower()
            return {"tipo": tipo, "documentos": claims_ai.documentos_para(tipo)}

        if name == "proponer_renovacion":
            pn = str(args.get("policy_number") or "").strip()
            if not pn:
                return {"error": "falta policy_number; pídele al cliente su número de póliza"}
            try:
                row = conn.execute(
                    """SELECT p.policy_number, p.end_date, p.status::text status,
                              p.monthly_premium_cop::float prima_actual_cop,
                              pr.insurance_type::text tipo, c.full_name
                       FROM public.policies p
                       JOIN public.customers c ON c.id = p.customer_id
                       JOIN public.quotes q ON q.id = p.quote_id
                       JOIN public.products pr ON pr.id = q.product_id
                       WHERE p.policy_number ILIKE %s""", (pn,)).fetchone()
            except Exception:
                conn.rollback()
                row = None
            if not row:
                return {"error": f"no encontré la póliza {pn}; verifica el número con el cliente"}
            from datetime import date as _date
            dias = (row["end_date"] - _date.today()).days
            perfil = None
            try:
                from . import profiling
                datos = {**_get_intake(conn, session_key), **_get_checkout(conn, session_key)}
                if datos:
                    perfil = profiling.build_profile(datos)
            except Exception:
                log.debug("perfil no disponible para renovar", exc_info=True)
            opciones = recommend(conn, country="CO", tipo=row["tipo"], age=None,
                                 sum_assured_usd=None, budget_monthly_usd=None,
                                 extras={}, perfil=perfil)
            for o in opciones:
                o.pop("breakdown", None)
            return {"poliza": {"numero": row["policy_number"], "tipo": row["tipo"],
                               "estado": row["status"], "titular": row["full_name"],
                               "prima_actual_cop": row["prima_actual_cop"],
                               "vence_en_dias": dias},
                    "opciones_renovacion": opciones,
                    "mensaje": ("Presenta la mejor opción de renovación comparándola con la "
                                "prima actual y ofrece cerrar la renovación aquí mismo "
                                "(mismo flujo: consentimiento → pago → emitir_poliza).")}

        # ---------- Pagos reales (Polar sandbox / modo demo) ----------
        if name in ("generar_link_pago", "verificar_pago", "solicitar_aclaracion"):
            from . import payments
            fn = {"generar_link_pago": payments.generar_link_pago,
                  "verificar_pago": payments.verificar_pago,
                  "solicitar_aclaracion": payments.solicitar_aclaracion}[name]
            return fn(conn, session_key, tenant_id, args)

        if name == "obtener_insights":
            if role != "gerente":
                return {"error": "acceso denegado: solo gerentes"}
            return insights_summary(conn)

        if name == "listar_leads":
            if role != "gerente":
                return {"error": "acceso denegado: solo gerentes"}
            rows = conn.execute(
                """SELECT l.name, l.country, l.stage, l.updated_at, COUNT(q.id) cotizaciones,
                          ROUND(COALESCE(SUM(q.premium_monthly_usd),0)::numeric,2)::double precision prima_usd
                   FROM leads l LEFT JOIN quotes q ON q.lead_id=l.id
                   GROUP BY l.id ORDER BY l.updated_at DESC LIMIT %s""",
                (min(int(args.get("limit", 20)), 100),)).fetchall()
            return [dict(r) for r in rows]

        # ---------- Intake / información real / perfilamiento ----------
        # Particionado por (tenant_id, user_id); user_id = phone o 'web:anon'.
        skey = f"{tenant_id}:{phone or 'web:anon'}"

        if name == "solicitar_informacion":
            from . import intake
            tipo = (args.get("insurance_type") or "").lower()
            datos = _get_intake(conn, skey)
            comp = intake.completitud(tipo, datos)
            comp["documentos_sugeridos"] = intake.documentos_sugeridos(tipo)
            return comp

        if name == "guardar_datos_cliente":
            campos = args.get("campos") or {}
            if not isinstance(campos, dict) or not campos:
                return {"error": "envía 'campos' como objeto {id_campo: valor}"}
            datos = _save_intake(conn, skey, campos)
            return {"ok": True, "guardados": list(campos.keys()), "total_campos": len(datos)}

        if name == "generar_formulario":
            from . import intake
            tipo = (args.get("insurance_type") or "").lower()
            datos = _get_intake(conn, skey)
            return {"formulario": intake.spec_formulario(tipo, datos)}

        if name == "analizar_documento":
            try:
                from . import files
            except Exception as exc:
                return {"error": f"lectura de archivos no disponible: {exc}"}
            fid = args.get("file_id") or ""
            path = files.path_for(fid) if hasattr(files, "path_for") else fid
            parsed = files.parse_document(path)
            campos = parsed.get("campos_extraidos") or {}
            if campos:
                _save_intake(conn, skey, campos)
            # Si es un documento del expediente KYC (tipo explícito o detectado),
            # queda registrado además en kyc_document para el gate de emisión.
            from . import kyc
            tipo_kyc = args.get("tipo") or {"cedula": "cedula_frente",
                                            "tarjeta_propiedad": "tarjeta_propiedad"}.get(
                                                parsed.get("tipo_detectado") or "")
            registrado = None
            if tipo_kyc:
                real_phone = phone if phone and not phone.startswith("web:") else None
                kyc.register_document(conn, session_key, tipo=tipo_kyc, file_id=fid,
                                      path=path, extracted=campos, phone=real_phone)
                registrado = tipo_kyc
            return {"tipo_detectado": parsed.get("tipo_detectado"),
                    "campos_extraidos": campos, "resumen": parsed.get("resumen"),
                    "documento_kyc_registrado": registrado}

        if name == "registrar_documento_kyc":
            from . import kyc
            try:
                from . import files
            except Exception as exc:
                return {"error": f"lectura de archivos no disponible: {exc}"}
            fid = str(args.get("file_id") or "").strip()
            tipo = str(args.get("tipo") or "").strip()
            if not fid or not tipo:
                return {"error": "faltan file_id y/o tipo del documento"}
            path = files.path_for(fid) if hasattr(files, "path_for") else fid
            real_phone = phone if phone and not phone.startswith("web:") else None
            kyc.register_document(conn, session_key, tipo=tipo, file_id=fid, path=path,
                                  phone=real_phone)
            st = kyc.status(conn, session_key, args.get("insurance_type"))
            return {"ok": True, "registrado": tipo, "faltantes": st["faltantes"],
                    "listo_para_emitir": st["listo_para_emitir"]}

        if name == "verificar_identidad":
            from . import kyc
            real_phone = phone if phone and not phone.startswith("web:") else None
            verdict = kyc.run_verification(conn, session_key, phone=real_phone,
                                           doc_file_id=args.get("doc_file_id"),
                                           selfie_file_id=args.get("selfie_file_id"))
            msg = {
                "aprobado": "Identidad verificada: el rostro coincide con la cédula. Puedes continuar con el cierre.",
                "rechazado": "El rostro de la selfie NO coincide con el de la cédula. Pide una selfie clara, de frente y bien iluminada, o una mejor foto de la cédula (máx. 2 intentos).",
                "revision": "No se pudo comparar (rostro no detectado o falta un documento). Pide de nuevo la foto de la cédula (frente) y una selfie nítida.",
                "no_disponible": "El motor de verificación no está disponible ahora; avísale al cliente que un asesor validará su identidad y sigue registrando el resto del expediente.",
            }.get(verdict.get("decision"), "")
            return {**verdict, "mensaje": msg}

        if name == "estado_kyc":
            from . import kyc
            return kyc.status(conn, session_key, args.get("insurance_type"))

        if name == "perfilar_cliente":
            try:
                from . import profiling
            except Exception as exc:
                return {"error": f"perfilamiento no disponible: {exc}"}
            datos = _get_intake(conn, skey)
            merged = {**datos, **_get_checkout(conn, skey)}
            return profiling.build_profile(merged)

        if name == "suscribir_informes":
            try:
                from . import reports as reports_mod
            except Exception as exc:
                return {"error": f"informes no disponibles: {exc}"}
            real_phone = phone if phone and not phone.startswith("web:") else None
            out = reports_mod.subscribe(
                str(args.get("email") or ""), tipo="cliente",
                frecuencia=str(args.get("frecuencia") or "mensual"),
                phone=real_phone)
            if "error" in out:
                return out
            return {**out, "mensaje": ("Suscripción registrada. Confírmale al cliente "
                                       "que recibirá su informe y con qué frecuencia.")}

        return {"error": f"herramienta desconocida: {name}"}
    finally:
        conn.close()


# ---------- Historial de sesión (PostgreSQL) ----------

def _history_table(conn: psycopg.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS chat_history (
        session_id TEXT, seq INTEGER, message TEXT,
        PRIMARY KEY (session_id, seq))""")


def _load_history(session_id: str, limit: int = 30) -> list[dict]:
    conn = get_conn()
    _history_table(conn)
    rows = conn.execute(
        "SELECT message FROM chat_history WHERE session_id=%s ORDER BY seq DESC LIMIT %s",
        (session_id, limit)).fetchall()
    conn.close()
    msgs = [json.loads(r["message"]) for r in reversed(rows)]
    # La ventana no debe empezar con un 'tool' huérfano ni con un 'assistant' con
    # tool_calls cuyos 'tool' quedaron fuera: la API exige que cada 'tool' siga a su
    # 'assistant'+tool_calls. Recorta el prefijo hasta el primer 'user'.
    for i, m in enumerate(msgs):
        if m.get("role") == "user":
            return msgs[i:]
    return []


def _append_history(session_id: str, messages: list[dict]) -> None:
    conn = get_conn()
    _history_table(conn)
    row = conn.execute("SELECT COALESCE(MAX(seq),0) m FROM chat_history WHERE session_id=%s",
                       (session_id,)).fetchone()
    seq = row["m"]
    for m in messages:
        seq += 1
        conn.execute("INSERT INTO chat_history (session_id, seq, message) VALUES (%s,%s,%s)",
                     (session_id, seq, json.dumps(m, ensure_ascii=False)))
    conn.commit()
    conn.close()


# ---------- Loop principal ----------

SUGERENCIAS_RE = re.compile(r"\n?SUGERENCIAS:\s*(.+)\s*$", re.IGNORECASE)

DOC_CLAIM_RE = re.compile(r"(te (lo |la )?(envié|envío|mando|mandé)|adjunto|aquí tienes (el|tu) (pdf|documento|cotización))", re.IGNORECASE)


def run_agent(session_id: str, user_message: str, *, phone: str = "",
              role: str = "cliente", tenant_id: str = "demo") -> dict:
    """Un turno completo del agente: historial → LLM → herramientas (multi-ronda) → respuesta.

    `tenant_id` (organización) y `phone`/user_id (cliente) se propagan como argumentos por
    TODA la cadena; nunca se guardan en el módulo/singleton (patrón Paloma)."""
    if not DEEPSEEK_API_KEY:
        return {"error": "llm_no_configurado",
                "reply": "El motor conversacional no está configurado (falta DEEPSEEK_API_KEY). "
                         "Puedes usar el cotizador rápido mientras tanto."}
    from openai import OpenAI
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL,
                    timeout=30.0, max_retries=2)

    if not phone:
        phone = f"web:{session_id}"
    if role != "gerente" and phone in MANAGER_PHONES:
        role = "gerente"
    system = SYSTEM_PROMPT_GERENTE if role == "gerente" else SYSTEM_PROMPT_CLIENTE
    # Conocimiento del negocio editable por gerencia (panel "Agente IA" del
    # CRM): promos, políticas, aclaraciones de precios. Devuelve "" si no hay
    # entradas o la BD falla — nunca rompe el turno.
    from .knowledge import knowledge_context
    system += knowledge_context(tenant_id)

    hist_key = f"{tenant_id}:{session_id}"  # historial particionado por (tenant_id, sesión)
    history = _load_history(hist_key)
    messages = [{"role": "system", "content": system}, *history,
                {"role": "user", "content": user_message}]
    new_msgs: list[dict] = [{"role": "user", "content": user_message}]
    actions: list[dict] = []
    tools_called: set[str] = set()

    reply = ""
    doc_claim_pending = False
    try:
        for _round in range(MAX_TOOL_ROUNDS):
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL, messages=messages, tools=TOOLS_SCHEMA,
                temperature=0.6, max_tokens=900)
            msg = resp.choices[0].message
            if msg.tool_calls:
                assistant_msg = {"role": "assistant", "content": msg.content or "",
                                 "tool_calls": [tc.model_dump() for tc in msg.tool_calls]}
                messages.append(assistant_msg)
                new_msgs.append(assistant_msg)
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    log.info("tool %s(%s)", tc.function.name, args)
                    try:
                        result = _exec_tool(tc.function.name, args, phone=phone, role=role,
                                            tenant_id=tenant_id)
                    except Exception as exc:  # una herramienta que falla no tumba el turno
                        log.exception("tool %s falló", tc.function.name)
                        result = {"error": f"la herramienta falló: {exc}"}
                    tools_called.add(tc.function.name)
                    action = {"tool": tc.function.name, "args": args}
                    if isinstance(result, dict) and result.get("download_url"):
                        action["download_url"] = result["download_url"]
                    if isinstance(result, dict) and result.get("policyNumber"):
                        action["policyNumber"] = result["policyNumber"]
                    actions.append(action)
                    tool_msg = {"role": "tool", "tool_call_id": tc.id,
                                "content": json.dumps(result, ensure_ascii=False, default=str)[:6000]}
                    messages.append(tool_msg)
                    new_msgs.append(tool_msg)
                continue
            reply = msg.content or ""
            # Red de seguridad: afirma haber entregado un documento sin herramienta
            if DOC_CLAIM_RE.search(reply) and "generar_documento" not in tools_called and role == "cliente":
                doc_claim_pending = True
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content":
                                 "[sistema] Afirmaste entregar un documento sin generar ninguno. "
                                 "Llama la herramienta generar_documento con el quote_id correcto o corrige tu mensaje."})
                continue
            doc_claim_pending = False
            break
        else:
            reply = reply or "Estoy teniendo un problema técnico para completar esto. ¿Lo intentamos de nuevo?"
    except Exception as exc:  # error de red/API del LLM
        log.exception("fallo del LLM")
        return {"error": "llm_error", "reply":
                "Estoy teniendo un problema técnico en este momento. Intenta de nuevo en "
                "unos segundos, o usa el cotizador rápido mientras tanto.",
                "quick_replies": [], "actions": [], "role": role, "documents": []}

    # #8: si terminó afirmando un documento que nunca generó, no engañes al cliente
    if doc_claim_pending and "generar_documento" not in tools_called:
        reply = ("Puedo prepararte la cotización formal en PDF ahora mismo. "
                 "¿Confirmas la opción que te interesa para generarla?")

    quick_replies: list[str] = []
    m = SUGERENCIAS_RE.search(reply)
    if m:
        quick_replies = [s.strip() for s in m.group(1).split("|") if s.strip()][:3]
        reply = SUGERENCIAS_RE.sub("", reply).strip()

    new_msgs.append({"role": "assistant", "content": reply})
    _append_history(hist_key, new_msgs)

    documents = [a["download_url"] for a in actions if a.get("download_url")]
    return {"reply": reply, "quick_replies": quick_replies, "actions": actions,
            "role": role, "documents": documents}
