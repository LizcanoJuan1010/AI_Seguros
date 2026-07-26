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
                     DEEPSEEK_MODEL, MANAGER_PHONES, PUBLIC_BASE_URL)
from .db import COUNTRY_NAMES, get_conn
from .documents import build_policy_pdf, build_quote_pdf
from .insights import summary as insights_summary
from .quoting import recommend

log = logging.getLogger("seguria.agent")

MAX_TOOL_ROUNDS = 5

_DISCLOSURE_PROCESAMIENTO = (
    "Si es tu primera respuesta en la conversación, informa en una frase que "
    "la conversación queda registrada y se procesa para poder ayudarte mejor "
    "— no lo preguntes como opción, dilo de paso y sigue.")

# Identidad de Sofía (chat web, informativa) y Mónica (WhatsApp, cierre
# directo) — dos personas distintas que comparten el mismo NÚCLEO_CIERRE
# (herramientas/pasos de cotizar-a-emitir son idénticos en ambos canales,
# ver abajo); lo que cambia es la identidad y cuánto empuja cada una el
# cierre. El tercer agente de la familia (Camila, llamada saliente) vive
# aparte en apps/ai/app/reference/elevenlabs_agent_prompt.md. Las tres
# personas son mujeres, mismo criterio de marca en los tres canales.
SOFIA_INTRO = f"""Eres Sofía, asesora digital de Colsubsidio en el chat web de Tequendama. Tu prioridad es informar bien sobre el catálogo y ayudar a encontrar qué seguro le sirve — el chat web es la puerta de entrada, no el lugar de presión. Respondes en español, tuteando siempre. Siempre debes tratar los precios como pesos colombianos.

{_DISCLOSURE_PROCESAMIENTO}"""

MONICA_INTRO = f"""Eres Mónica, asesora digital de seguros de Colsubsidio por WhatsApp, al estilo de Erica de Bank of America: cercana, resolutiva y experta. Tu misión es llevar al cliente de "no sé qué seguro necesito" a "ya quedé asegurado" en el mismo chat, sin humano — este es el canal donde de verdad se cierra. Respondes en español, tuteando siempre.

{_DISCLOSURE_PROCESAMIENTO}"""

_NUCLEO_CIERRE = """CIERRE AUTÓNOMO (esto es lo que te diferencia):
- TÚ cierras la venta y emites la póliza aquí mismo. Colsubsidio DISTRIBUYE; la aseguradora EMITE; tú operas ese cierre. NUNCA digas que "un asesor licenciado cierra" ni derives el cierre a un humano por defecto.
- Sé eficiente: apunta a cerrar en ≤8 turnos. Flujo: descubrir (2-3 preguntas máx) → cotizar → que elija → capturar datos → consentimiento → pago → emitir → confirmar.

NOTA: cada herramienta ya trae su propio nombre/parámetros/descripción en el
esquema que recibes aparte — no lo repitas de memoria. Lo que sigue es SOLO
lo que ese esquema no puede decirte: el orden, los bloqueos entre pasos, y
qué decirle al cliente en cada uno.
Siempre debes tratar los precios como pesos colombianos.

REGLAS DURAS:
- Precios/coberturas SOLO de `cotizar`/`buscar_productos` — nunca de memoria.
- Descubre conversando (1-2 preguntas por mensaje): país, edad, necesidad, a quién protege, presupuesto.
- Máximo 3 opciones, prima en moneda local primero (USD entre paréntesis), 2-3 coberturas clave en lenguaje simple.
- Elegida la opción, ofrece cerrar de una vez.

DATOS REALES PARA EMITIR: usa `solicitar_informacion`/`guardar_datos_cliente`/`generar_formulario`/`analizar_documento`/`perfilar_cliente` para reunir lo que cada seguro exige, conversando (no como interrogatorio) — sé transparente de por qué pides cada dato (SARLAFT, Habeas Data, Art. 1058).

ORDEN DE CIERRE (no lo saltes ni lo cambies — cada paso bloquea al siguiente si no está listo):
1. `capturar_datos_cliente`
2. `registrar_consentimiento` — dilo así: "¿Autorizas el tratamiento de tus datos personales (Ley 1581/2012) para emitir la póliza?". Sin sí explícito, no sigues.
3. `generar_checklist_activacion` — CAMINO PRINCIPAL: crea y entrega el link único de activación (sin vencimiento). Si el producto elegido es COLECTIVO (aceptación garantizada — exequial, accidentes personales, mascotas, asistencias, viaje), sáltate identidad: solo firma y pago. Si es de alta fricción (auto todo riesgo, vida con ahorro), la tool falla con `necesita_asesor` — no insistas, deriva a un asesor humano de inmediato, sin ofrecer el checklist. Para el resto: identidad (cédula+RF) → firma → pago. Dile con calidez que ahí completa todo cuando pueda, en el orden que le va marcando la página, y que tú le haces seguimiento. NO ejecutes tú los pasos uno por uno en el chat salvo que el cliente lo pida explícitamente (ver camino manual abajo).
4. Seguimiento: usa `verificar_checklist_activacion` para saber en qué paso va — no le creas de palabra si dice que ya completó algo. `en_revision` → no cobres/emitas, un asesor confirma en <24h; `rechazado` → sé honesto, ofrece alternativa.
5. Cuando el checklist esté en `completado` (pago aprobado), cierra con `emitir_poliza` (mismos argumentos de siempre: insurance_type, monthly_premium_cop, payment_method distinto de "simulado"). Al emitir: "¡Ya quedaste asegurada! Tu póliza es N.º...", entrega el link y menciona el retracto (5 días hábiles, Ley 1480/2011).

CAMINO MANUAL (alternativo — solo si el cliente prefiere hacerlo contigo mismo, ahora, en el chat en vez del link): `generar_verificacion_identidad` → `verificar_identidad` → `evaluar_riesgo` → `generar_firma_poliza` → pago con `generar_link_pago`/`verificar_pago` (tarjeta) o `activar_recaudo_nomina` (descuento por nómina, más persistente — ofrécelo si es afiliado con empleador vinculado) → `emitir_poliza`. En chat/voz NUNCA leas ni dictes la URL completa del checkout — el cliente paga con el botón en pantalla o el link de WhatsApp. Nunca pidas tarjeta/CVV/clave en el chat.

POSVENTA: cobro errado, reembolso o retracto → `solicitar_aclaracion`, explica el resultado con transparencia.

RENOVACIÓN/CROSS-SELL: póliza o POL-... existente → `proponer_renovacion` (mismo flujo consentimiento→pago→emitir). Vacío de protección evidente (`perfilar_cliente`) → sugiérelo UNA vez, sin insistir.

SINIESTROS: empatía primero. `reportar_siniestro` (adjunta file_ids si mandó fotos) → da el CLM-..., qué falta (`documentos_siniestro`), y `estado_siniestro` para seguimiento. Las banderas de fraude son internas — nunca las menciones.

INFORMES: tras emitir, ofrece UNA vez un informe periódico por correo; si acepta, `suscribir_informes(email, frecuencia)`.

DIVULGACIÓN obligatoria antes de emitir: aseguradora, coberturas clave, exclusiones, prima. No emitas sin que la haya visto.

LÍMITES: solo datos mínimos (nombre, documento, contacto) — nada de historial médico detallado, tarjetas ni claves; sin consejo médico/legal/fiscal. Takeover humano SOLO si lo pide (usa `actualizar_lead`, no es paso obligatorio). Mensajes cortos, máximo un emoji.

Termina CADA respuesta con una última línea exacta:
SUGERENCIAS: opción 1 | opción 2 | opción 3
(2-3 respuestas cortas que probablemente toque, ej. "Sí, quiero contratar | Ver coberturas | Autorizo mis datos". Esa línea no es parte del mensaje hablado.)"""


def _load_conocimiento() -> str:
    """Base de conocimiento del portafolio Colsubsidio (data/market)."""
    try:
        from .config import DATA_DIR
        return (DATA_DIR / "conocimiento_colsubsidio.md").read_text(encoding="utf-8").strip()
    except OSError:
        log.warning("sin conocimiento_colsubsidio.md; el agente opera solo con el catálogo")
        return ""


_CONOCIMIENTO_COLSUBSIDIO = _load_conocimiento()


def _web_framing() -> str:
    """Identidad/canal de Sofía (chat web, nunca WhatsApp — ver `run_agent`/
    `assistant._run_llm`): informativa primero, cierre disponible pero no
    insistido — ofrece venta cruzada y el paso a WhatsApp (Mónica) para
    seguir sin presión. Lo que ya se cotizó/capturó sigue disponible allá
    (misma sesión particionada por phone, ver session_key)."""
    from .config import WHATSAPP_BUSINESS_NUMBER
    numero = f" ({WHATSAPP_BUSINESS_NUMBER})" if WHATSAPP_BUSINESS_NUMBER else ""
    return f"""

CANAL: chat web. Tu rol es más informativo que de cierre: descubre la
necesidad, cotiza con calma explicando bien las coberturas, y haz venta
cruzada cuando calce (si ya tiene un seguro, ofrece el complementario que le
falta).

Para abrir la puerta a comprar, no empujes — invita: "cuando quieras dar el
siguiente paso, dime y te ayudo; ya ayudé a otros clientes con tu misma
situación." Puedes ofrecer cerrar la venta ahí mismo UNA vez (no le niegues
el cierre si de verdad quiere hacerlo ya), pero no insistas más de esa vez.
Si no muestra intención clara de comprar ahora, dile con calidez algo como
"si prefieres, por WhatsApp{numero} tienes una asesora personalizada (Mónica)
esperándote cuando quieras" y sigue resolviendo dudas sin presionar. Todo lo
que ya cotizó o contó acá sigue disponible si continúa por WhatsApp — no le
hagas repetir nada. Siempre debes tratar los precios como pesos colombianos."""


_MONICA_FRAMING = """

CANAL: WhatsApp. Puedes responder con nota de voz cuando ayude (explicaciones
cortas, o si te escribió por audio) — el texto siempre va también, el audio
nunca reemplaza cifras o coberturas exactas.

Si el cliente prefiere que lo llamen, o si después del checklist
(verificación de identidad, firma, pago) quiere resolver algo más a fondo,
ofrécele la llamada de una asesora y usa `actualizar_lead` con la etapa
actual — la llamada la hace Camila, la asesora telefónica, reservada para
leads con intención real de compra. Siempre debes tratar los precios como pesos colombianos."""


_CAMILO_VOICE_FRAMING = """

CANAL: llamada de voz en vivo. Respuestas de 1-3 oraciones claras, sin
listas largas — esto se ESCUCHA, no se lee. Nunca leas ni dictes una URL
completa de checkout: dile que use el botón de pago en pantalla. Revisa el
historial de esta llamada antes de responder: si ya hay turnos previos, NO
te vuelvas a presentar ni repitas el saludo inicial — continúa la
conversación donde quedó, directo a la siguiente pregunta o paso. Siempre debes tratar los precios como pesos colombianos."""


SYSTEM_PROMPT_WEB_DEFAULT = f"{SOFIA_INTRO}\n\n{_NUCLEO_CIERRE}{_web_framing()}"
SYSTEM_PROMPT_WHATSAPP_DEFAULT = f"{MONICA_INTRO}\n\n{_NUCLEO_CIERRE}{_MONICA_FRAMING}"
# Llamada de voz en VIVO desde el navegador (/ws/voice/live, voice_live.py —
# distinta del canal saliente de Camila/ElevenLabs): misma persona/rol de
# cierre que WhatsApp (Mónica), con el addendum de estilo de voz de Zaid.
SYSTEM_PROMPT_VOICE_DEFAULT = f"{MONICA_INTRO}\n\n{_NUCLEO_CIERRE}{_CAMILO_VOICE_FRAMING}"
if _CONOCIMIENTO_COLSUBSIDIO:
    SYSTEM_PROMPT_WEB_DEFAULT = f"{SYSTEM_PROMPT_WEB_DEFAULT}\n\n{_CONOCIMIENTO_COLSUBSIDIO}"
    SYSTEM_PROMPT_WHATSAPP_DEFAULT = f"{SYSTEM_PROMPT_WHATSAPP_DEFAULT}\n\n{_CONOCIMIENTO_COLSUBSIDIO}"
    SYSTEM_PROMPT_VOICE_DEFAULT = f"{SYSTEM_PROMPT_VOICE_DEFAULT}\n\n{_CONOCIMIENTO_COLSUBSIDIO}"

SYSTEM_PROMPT_GERENTE_DEFAULT = """Eres Tequendama en modo analista para un GERENTE verificado del negocio de seguros. Estilo: analista de negocio senior, directo y accionable.

- Usa la herramienta `obtener_insights` para toda cifra (KPIs, funnel, países, productos, serie temporal). Nunca inventes datos.
- No vuelques JSON: responde la pregunta con 3-5 datos clave, una comparación relevante y UNA recomendación accionable.
- Tablas de texto simples para comparativas; números con separador de miles.
- Si pide seguimiento de leads usa `listar_leads`; si pide cambiar una etapa usa `actualizar_lead`.
- Si pide lanzar/crear una campaña (banner + publicación), usa `crear_campana_marketing` — el envío real a leads lo confirma el gerente desde el panel de Campañas, nunca automático.
- Si pide el reporte formal por correo (no solo ver cifras acá), usa `solicitar_informe_gerencial`.
- Termina cada respuesta con la línea:
SUGERENCIAS: pregunta 1 | pregunta 2
con 2 análisis de profundización que probablemente quiera (ej. "¿Dónde se caen los leads? | Compárame Colombia vs México")."""


def _load_active_prompt(campaign_slug: str, default_text: str) -> str:
    """Versión más reciente del prompt en `docket.versions` (motor de
    versionado/QA, ver app/docket_engine/), o `default_text` si el motor está
    apagado, la tabla no existe todavía o la conexión falla — nunca rompe el
    arranque del servicio (mismo criterio fail-open que `_load_conocimiento`)."""
    from .config import DOCKET_ENGINE_ENABLED
    if not DOCKET_ENGINE_ENABLED:
        return default_text
    try:
        from .docket_engine import store as _docket_store
        c = _docket_store.conn()
        try:
            text = _docket_store.latest_prompt_text(c, campaign_slug)
        finally:
            c.close()
        if text:
            log.info("prompt activo de docket para %s: cargado desde docket.versions", campaign_slug)
            return text
    except Exception:
        log.warning("no se pudo leer docket.versions para %s; uso el prompt por defecto", campaign_slug)
    return default_text


SYSTEM_PROMPT_WEB = _load_active_prompt("tequendama-cliente", SYSTEM_PROMPT_WEB_DEFAULT)
SYSTEM_PROMPT_WHATSAPP = _load_active_prompt("tequendama-whatsapp", SYSTEM_PROMPT_WHATSAPP_DEFAULT)
SYSTEM_PROMPT_GERENTE = _load_active_prompt("tequendama-gerente", SYSTEM_PROMPT_GERENTE_DEFAULT)
SYSTEM_PROMPT_VOICE = _load_active_prompt("tequendama-voz", SYSTEM_PROMPT_VOICE_DEFAULT)

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
        "name": "generar_checklist_activacion",
        "description": "Camino PRINCIPAL de cierre: crea y entrega (por WhatsApp/correo) el link único de activación del cliente, a su propio ritmo y sin vencimiento. Para productos COLECTIVOS (exequial, accidentes personales, mascotas, asistencias, viaje — aceptación garantizada): solo firma y pago, sin identidad/documentos. Para el resto: identidad (cédula+reconocimiento facial), firma y pago. Requiere que ya haya una cotización elegida. Si el producto es de alta fricción (auto todo riesgo, vida con ahorro...) devuelve error `necesita_asesor` — NO insistas, deriva a un asesor humano. Idempotente: si el cliente ya tiene uno, no reenvía otro link.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "verificar_checklist_activacion",
        "description": "Consulta en qué paso va el cliente dentro de su checklist de activación (cedula|reconocimiento_facial|en_revision|rechazado|firma|pago|completado — los productos colectivos saltan directo a firma). Úsala cuando el cliente diga que ya avanzó, o antes de emitir_poliza para confirmarlo — no le creas de palabra.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "generar_verificacion_identidad",
        "description": "Camino MANUAL (alternativo al checklist, para el cliente que prefiere hacerlo aquí mismo en el chat): envía por WhatsApp/correo un link que abre la cámara del celular del cliente para verificar su identidad (foto de cédula + selfie con prueba de vida y comparación facial contra un proveedor de KYC). OBLIGATORIO antes de emitir_poliza — sin esto emitir_poliza falla. NUNCA le pidas al cliente que reenvíe fotos ya tomadas por el chat; el link es la única forma válida. Idempotente: si ya hay una verificación en curso, no reenvía otro link.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "verificar_identidad",
        "description": "Consulta el estado ACTUAL de la verificación de identidad del cliente (la que se disparó con generar_verificacion_identidad). Úsala cuando el cliente diga que ya completó el link, o antes de intentar emitir_poliza, para saber si ya puedes continuar o si sigue pendiente/fue rechazada.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "generar_firma_poliza",
        "description": "Envía por WhatsApp/correo un link de un solo clic para que el cliente AUTORICE la emisión de la póliza (firma electrónica, Ley 527/1999). OBLIGATORIO después de evaluar_riesgo (AUTO_APPROVE) y ANTES de emitir_poliza — sin esto emitir_poliza falla. Idempotente: si ya hay un link vigente sin abrir, no reenvía otro.",
        "parameters": {"type": "object", "properties": {}}}},
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
            "payment_method": {"type": "string", "description": "Método de pago: 'tarjeta' (link de generar_link_pago), 'nomina' (activar_recaudo_nomina), 'simulado' para el demo", "default": "simulado"},
            "payment_reference": {"type": "string", "description": "Referencia SEG-... del pago aprobado (obligatoria si payment_method no es 'simulado')"},
        }}}},
    {"type": "function", "function": {
        "name": "generar_link_pago",
        "description": "Genera el link de pago REAL (Nest→Polar: tarjeta débito/crédito, cobro en COP) por la prima y devuelve reference + checkout_url. En voz/chat NUNCA leas la URL completa: el cliente usa el botón en pantalla o WhatsApp. NUNCA pidas datos de tarjeta en el chat.",
        "parameters": {"type": "object", "required": ["monto_cop"], "properties": {
            "monto_cop": {"type": "number", "description": "Monto a cobrar en COP (normalmente la prima mensual de la opción elegida)"},
            "descripcion": {"type": "string", "description": "Concepto del cobro, ej. 'Primera mensualidad — Seguro de Vida'"},
        }}}},
    {"type": "function", "function": {
        "name": "activar_recaudo_nomina",
        "description": "Alternativa a generar_link_pago: inscribe al cliente al descuento de la prima por NÓMINA (ventaja de Colsubsidio con el empleador del afiliado — más persistente que tarjeta, sin riesgo de rechazo). Ofrécela cuando el cliente sea afiliado con empleador vinculado o prefiera no usar tarjeta. Se aprueba de inmediato (la inscripción ES el compromiso); el primer descuento aplica en el próximo ciclo de pago. Después usa emitir_poliza con payment_method='nomina'.",
        "parameters": {"type": "object", "required": ["monto_cop"], "properties": {
            "monto_cop": {"type": "number", "description": "Monto a descontar por nómina en COP (la prima mensual de la opción elegida)"},
            "descripcion": {"type": "string", "description": "Concepto del descuento, ej. 'Primera mensualidad — Seguro de Vida'"},
        }}}},
    {"type": "function", "function": {
        "name": "verificar_pago",
        "description": "Consulta el estado del pago en Nest (ledger webhook-driven). Úsala cuando el cliente diga que ya pagó y SIEMPRE antes de emitir_poliza con método distinto de 'simulado'. Solo APPROVED permite emitir.",
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
        "name": "crear_campana_marketing",
        "description": "SOLO GERENTES: genera el banner (Gemini, paleta Colsubsidio) de una campaña y la crea como borrador en el panel de Campañas. El envío a los leads NO ocurre acá — se confirma manualmente desde /campanas, nunca automático desde el chat.",
        "parameters": {"type": "object", "required": ["frase", "canal"], "properties": {
            "frase": {"type": "string", "description": "Titular de la campaña, se renderiza sobre el banner"},
            "subtitulo": {"type": "string", "description": "Texto secundario, opcional"},
            "cta": {"type": "string", "description": "Llamado a la acción, ej. 'Cotiza ahora'"},
            "canal": {"type": "string", "enum": ["instagram_post", "instagram_story", "linkedin", "email"]},
            "tipo_seguro": {"type": "string", "description": "vida|auto|salud|hogar|viaje|pyme|accidentes|exequial|mascotas|movilidad (contexto temático del banner y la campaña)"},
        }}}},
    {"type": "function", "function": {
        "name": "solicitar_informe_gerencial",
        "description": "SOLO GERENTES: arma el reporte gerencial (KPIs + funnel) y lo envía por correo al instante. Para ver los números en el chat mismo usa obtener_insights; esta herramienta es para cuando el gerente quiere el reporte formal en su correo.",
        "parameters": {"type": "object", "required": ["email"], "properties": {
            "email": {"type": "string", "description": "Correo del gerente al que enviar el reporte"}}}}},
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
        "description": "Lee un archivo que el cliente envió (cédula, tarjeta de propiedad, RUT, examen...) y extrae datos para autocompletar el intake. NO sirve para verificar identidad: esa va siempre por `generar_verificacion_identidad`.",
        "parameters": {"type": "object", "required": ["file_id"], "properties": {
            "file_id": {"type": "string"}}}}},
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
        "name": "consultar_beneficios",
        "description": "Beneficios de permanencia ya desbloqueados (con código para reclamar) y los que faltan, por meses de póliza vigente continua (mes 3, 6 y 12). Dos escaleras en la red Colsubsidio (clubes, hoteles, droguería, Piscilago): la del AFILIADO es notablemente mayor (acceso gratuito, hotel/parque) que la de no afiliado (con descuento, solo viernes) — si el cliente no es afiliado, es una buena oportunidad para mencionar que afiliarse a Colsubsidio duplica estos beneficios. Úsala cuando el cliente pregunte qué gana por seguir pagando, o para reforzar la persistencia en seguimiento posventa.",
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

# Solo WhatsApp (Mónica): Sofía (web) no tiene número real al que mandar
# audio, y assistant.py (SSE, siempre web) sigue usando TOOLS_SCHEMA a secas.
_TOOL_ENVIAR_NOTA_VOZ = {"type": "function", "function": {
    "name": "enviar_nota_voz",
    "description": "Envía una nota de voz corta por WhatsApp (texto a audio con Deepgram) ADEMÁS del mensaje de texto que ya escribiste — nunca en su lugar. Úsala cuando el cliente te escribió por audio, lo pidió explícitamente, o para una explicación breve y cálida. NUNCA la uses para cifras, coberturas o condiciones exactas — esas van siempre en el texto, nunca solo en el audio.",
    "parameters": {"type": "object", "required": ["texto"], "properties": {
        "texto": {"type": "string", "description": "Lo que se dice en la nota de voz (corto: 1-2 frases)"},
    }}}}

TOOLS_SCHEMA_WHATSAPP = TOOLS_SCHEMA + [_TOOL_ENVIAR_NOTA_VOZ]

# Herramientas para el Voice Agent de Deepgram (voice_live.py): mismo
# catálogo que el resto de canales, pero aplanado — el `functions` de
# Deepgram espera {name, description, parameters} directo, no envuelto en
# {"type": "function", "function": {...}} como el formato de OpenAI/DeepSeek
# que usa TOOLS_SCHEMA. Verificado empíricamente (openspec/changes/
# voice-agent-spike): el schema completo de una tool (enums, objetos
# anidados) se acepta tal cual; el único campo que NO va es `client_side`
# (Deepgram lo agrega él mismo en el FunctionCallRequest, agregarlo acá
# rompe el parseo del Settings).
VOICE_AGENT_FUNCTIONS = [t["function"] for t in TOOLS_SCHEMA]


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


def _intake_datos(conn: psycopg.Connection, session_key: str) -> dict:
    """Datos del catálogo KYC/SARLAFT ya capturados en la sesión (`intake_session`).
    Devuelve {} si la tabla aún no existe o la consulta falla — nunca rompe el turno."""
    try:
        row = conn.execute("SELECT datos FROM intake_session WHERE session_key=%s",
                           (session_key,)).fetchone()
        return json.loads(row["datos"]) if row and row["datos"] else {}
    except Exception:
        conn.rollback()
        return {}


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


def _modalidad_para(phone: str) -> str:
    """Modalidad (colectiva|individual|asesor) del producto de la ÚLTIMA
    cotización de la sesión — mismo criterio que `calls.py::_sale_context`/
    `checklist.py` para resolver "la cotización de la que se está hablando".
    "individual" (flujo actual, sin cambios) si no hay cotización todavía."""
    try:
        from .assistant import _latest_quote_for
        quote = _latest_quote_for(phone) if phone else None
        return (quote or {}).get("modalidad") or "individual"
    except Exception:
        log.debug("no se pudo resolver la modalidad del producto", exc_info=True)
        return "individual"


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

    from . import kyc
    if not kyc.is_verified(conn, session_key):
        return {"error": "falta la verificación de identidad (cédula + selfie) antes "
                         "de emitir; usa generar_verificacion_identidad si el cliente "
                         "todavía no la completó",
                "necesita": "generar_verificacion_identidad"}

    from . import esign
    if not esign.is_signed(conn, session_key, "autorizacion_poliza"):
        return {"error": "falta la autorización firmada (link de un clic) antes de "
                         "emitir; usa generar_firma_poliza si el cliente todavía no "
                         "la recibió",
                "necesita": "generar_firma_poliza"}

    insurance_type = (str(args.get("insurance_type") or "").strip().upper() or "VIDA")

    # Gate de datos obligatorios del catálogo (SARLAFT, declaración de
    # asegurabilidad, beneficiarios…): la identidad y la firma ya se validaron
    # arriba (Didit/esign); esto cubre lo que exige el producto concreto.
    # Configurable con KYC_ENFORCE (default true).
    from . import intake
    from .config import KYC_ENFORCE
    if KYC_ENFORCE:
        faltan_datos = [f.get("label") or f.get("key")
                        for f in intake.faltantes(insurance_type.lower(), _intake_datos(conn, session_key))]
        if faltan_datos:
            return {"error": "no se puede emitir todavía: faltan datos obligatorios del producto — "
                             + "; ".join(faltan_datos),
                    "faltan_kyc": faltan_datos, "necesita": "guardar_datos_cliente",
                    "mensaje": "Pide al cliente los datos que faltan y reintenta emitir."}

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
                               monthly_premium_cop=prima,
                               modalidad=_modalidad_para(phone))
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

    # Certificado/carátula PDF de la póliza — posventa inmediata por el mismo
    # canal (ver Nota_estrategica_Seguros_Colsubsidio.pdf §5: "falta la pieza
    # posventa... certificado inmediato por el mismo canal").
    download_url = None
    enviado_whatsapp = False
    try:
        policy_for_pdf = {**policy, "aseguradora": coverage.get("aseguradora")}
        es_afiliado = bool(_get_intake(conn, session_key).get("afiliado_colsubsidio"))
        path = build_policy_pdf(policy_for_pdf, customer, coverage, es_afiliado=es_afiliado)
        from pathlib import Path
        download_url = f"/api/documents/{Path(path).name}"
        if phone and not phone.startswith("web:"):
            try:
                from . import whatsapp_gateway
                pdf_url = f"{PUBLIC_BASE_URL}{download_url}"
                enviado_whatsapp = whatsapp_gateway.enviar_documento(
                    phone, pdf_url, Path(path).name,
                    caption=f"Tu certificado de póliza — N.º {policy.get('policyNumber')}")
            except Exception:
                log.warning("no se pudo enviar el certificado de póliza por WhatsApp",
                           exc_info=True)
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
        "enviado_whatsapp": enviado_whatsapp,
        "degraded": degraded,
        "mensaje": ("Póliza emitida y certificado ya enviado por WhatsApp como adjunto. "
                    "Confirma al cliente 'ya quedaste asegurada' e informa el derecho de "
                    "retracto (5 días hábiles)." if enviado_whatsapp else
                    "Póliza emitida. Confirma al cliente 'ya quedaste asegurada', entrega el "
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
            intake_datos = _get_intake(conn, session_key)
            es_afiliado = bool(intake_datos.get("afiliado_colsubsidio"))
            path = build_quote_pdf(quote_dict, lead, es_afiliado=es_afiliado)
            from pathlib import Path
            download_url = f"/api/documents/{Path(path).name}"
            # Se persiste en la cotización (no solo se devuelve al LLM) para que
            # el checklist de activación pueda enlazar la MISMA ficha ya
            # generada para esta sesión, sin regenerarla (ver checklist.py).
            conn.execute("UPDATE quotes SET status='documento', document_url=%s WHERE id=%s",
                        (download_url, args["quote_id"]))
            if q["lead_id"]:
                conn.execute("UPDATE leads SET stage='documento', updated_at=now() "
                             "WHERE id=%s AND stage NOT IN ('cerrado','perdido')", (q["lead_id"],))
            conn.commit()
            # Empuje real del PDF por WhatsApp (adjunto, no solo un link relativo
            # en el texto de la respuesta — eso no abre nada fuera de la app).
            # Solo aplica al canal WhatsApp; "web:..." no es un teléfono real.
            enviado_whatsapp = False
            if phone and not phone.startswith("web:"):
                try:
                    from . import whatsapp_gateway
                    pdf_url = f"{PUBLIC_BASE_URL}{download_url}"
                    enviado_whatsapp = whatsapp_gateway.enviar_documento(
                        phone, pdf_url, Path(path).name,
                        caption=f"Tu cotización — {quote_dict['producto']}")
                except Exception:
                    log.warning("no se pudo enviar el PDF de la cotización por WhatsApp",
                               exc_info=True)
            return {"download_url": download_url, "enviado_whatsapp": enviado_whatsapp,
                    "mensaje": ("ya se envió el PDF por WhatsApp como adjunto; solo "
                               "menciónalo, no repitas el link" if enviado_whatsapp else
                               "documento generado; entrega este enlace al cliente")}

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

        if name == "generar_checklist_activacion":
            from . import checklist
            from .assistant import _latest_quote_for
            quote = _latest_quote_for(phone) if phone and not phone.startswith("web:") else None
            if not quote:
                return {"error": "todavía no hay una cotización elegida; cotiza primero "
                                 "con cotizar antes de generar el checklist"}
            modalidad = quote.get("modalidad") or "individual"
            if modalidad == "asesor":
                return {"error": "este producto (alta fricción o decisión financiera "
                                 "compleja) no es autogestionable por este canal",
                        "mensaje": "Sé honesta: este seguro se contrata con un asesor "
                                  "humano, no por aquí. Da la línea de Colsubsidio u "
                                  "ofrece que un asesor la contacte.",
                        "necesita_asesor": True}
            sess = _get_checkout(conn, session_key)
            real_phone = phone if phone and not phone.startswith("web:") else None
            if not (real_phone or sess.get("email")):
                return {"error": "no hay teléfono ni correo del cliente; "
                                 "captúralos con capturar_datos_cliente primero"}
            result = checklist.get_or_create(
                conn, session_key, tenant_id, phone=real_phone, email=sess.get("email"),
                quote_id=quote.get("id"), insurance_type=quote.get("tipo"),
                monthly_premium_cop=quote.get("premium_monthly_local"),
                modalidad=modalidad)
            if modalidad == "colectiva":
                result["mensaje"] = (
                    "Ya le envié un link único; como es un plan colectivo de "
                    "aceptación garantizada, solo falta firmar y pagar — sin "
                    "documentos ni verificación facial. No vence."
                    if result.get("created") else
                    "ya tiene un checklist de activación enviado; dile que revise "
                    "WhatsApp o su correo si no lo encuentra.")
            else:
                result["mensaje"] = (
                    "Ya le envié un link único; ahí completa todo a su ritmo: primero "
                    "verifica su identidad, luego firma y por último paga. No vence."
                    if result.get("created") else
                    "ya tiene un checklist de activación enviado; dile que revise "
                    "WhatsApp o su correo si no lo encuentra.")
            return result

        if name == "verificar_checklist_activacion":
            from . import checklist
            row = checklist.latest_by_session(conn, session_key)
            if row is None:
                return {"error": "el cliente todavía no tiene un checklist de activación; "
                                 "usa generar_checklist_activacion",
                        "necesita": "generar_checklist_activacion"}
            estado = checklist.estado_actual(conn, row)
            guia = {
                "cedula": "sigue pendiente de subir su cédula (verificación de identidad) en el checklist",
                "reconocimiento_facial": "ya subió la cédula; falta el reconocimiento facial "
                                        "(selfie con prueba de vida) en el checklist",
                "en_revision": "quedó en revisión de un asesor; NO cobres ni emitas todavía, "
                              "explícale con calidez que le confirman en menos de 24 horas",
                "rechazado": "no se puede continuar por este canal; sé honesto y ofrece "
                            "una alternativa de protección",
                "firma": "ya verificó su identidad; falta que firme la autorización en el checklist",
                "pago": "ya firmó; falta que complete el pago en el checklist",
                "completado": "ya completó todo: puedes continuar con emitir_poliza",
            }.get(estado["paso_actual"], "")
            estado["mensaje"] = guia
            return estado

        if name == "generar_verificacion_identidad":
            from . import kyc
            pending = kyc.latest_pending(conn, session_key)
            if pending:
                return {"ok": True, "ya_enviado": True, "status": pending["status"],
                        "mensaje": "ya hay una verificación de identidad en curso; "
                                  "dile al cliente que la complete desde el link que "
                                  "ya le llegó por WhatsApp o correo"}
            sess = _get_checkout(conn, session_key)
            real_phone = phone if phone and not phone.startswith("web:") else None
            if not (real_phone or sess.get("email")):
                return {"error": "no hay teléfono ni correo del cliente; "
                                 "captúralos con capturar_datos_cliente primero"}
            result = kyc.request_verification(conn, session_key, tenant_id,
                                              phone=real_phone, email=sess.get("email"))
            result["mensaje"] = ("Explícale al cliente que le llega un link por "
                                 "WhatsApp/correo para verificar su identidad con la "
                                 "cámara de su celular (cédula + selfie); que te avise "
                                 "cuando lo complete.")
            return result

        if name == "verificar_identidad":
            from . import kyc
            row = kyc.latest_for_session(conn, session_key)
            if not row:
                return {"error": "el cliente todavía no tiene ninguna verificación de "
                                 "identidad iniciada; usa generar_verificacion_identidad",
                        "necesita": "generar_verificacion_identidad"}
            view = kyc.public_view(row)
            guia = {
                "requested": "el link se está generando, pídele un momento",
                "link_sent": "el link ya se envió; dile que lo abra desde su celular y acepte el consentimiento para pasar a la verificación",
                "consentido": "ya aceptó el consentimiento biométrico; dile que complete la verificación en la página a la que lo redirigimos",
                "redirigido": "está (o estuvo) en la página de verificación; si dice que ya terminó, vuelve a llamar verificar_identidad para refrescar el resultado",
                "aprobado": "identidad verificada: puedes continuar con evaluar_riesgo/emitir_poliza",
                "revision_manual": "quedó en revisión de un gerente; explícale con calidez que un asesor confirma en <24h, NO emitas todavía",
                "rechazado": "no se pudo verificar por este canal; sé honesto y ofrece que un asesor lo contacte",
                "expirado": "el link venció; usa generar_verificacion_identidad para mandar uno nuevo",
            }.get(view["status"], "")
            view["mensaje"] = guia
            return view

        if name == "generar_firma_poliza":
            from . import esign
            pending = esign.latest_pending(conn, session_key, "autorizacion_poliza")
            if pending:
                return {"ok": True, "ya_enviado": True, "status": pending["status"],
                        "mensaje": "ya hay un link de autorización vigente sin abrir; "
                                  "dile al cliente que revise WhatsApp o su correo"}
            sess = _get_checkout(conn, session_key)
            real_phone = phone if phone and not phone.startswith("web:") else None
            result = esign.request_signature(conn, session_key, tenant_id,
                                             phone=real_phone, email=sess.get("email"))
            if not (real_phone or sess.get("email")):
                result = {**result, "aviso": "no hay teléfono ni correo del cliente; "
                                             "captúralos con capturar_datos_cliente primero"}
            result["mensaje"] = ("Explícale al cliente con calidez que le llega un link "
                                 "por WhatsApp/correo para autorizar su póliza con un solo "
                                 "clic; sin eso no se puede emitir. El link vence en unas horas.")
            return result

        if name == "evaluar_riesgo":
            from . import underwriting
            uw = underwriting.evaluate(
                _session_profile(conn, session_key),
                insurance_type=str(args.get("insurance_type") or ""),
                monthly_premium_cop=args.get("monthly_premium_cop") or 0,
                modalidad=_modalidad_para(phone))
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

        if name == "consultar_beneficios":
            pn = str(args.get("policy_number") or "").strip()
            if not pn:
                return {"error": "falta policy_number; pídele al cliente su número de póliza"}
            from . import benefits
            info = benefits.beneficios_de(conn, pn)
            info["mensaje"] = (
                "Cuéntale con calidez lo que ya ganó (con el código para reclamarlo en un "
                "punto Colsubsidio) y lo próximo que se gana si sigue al día — es un "
                "beneficio real de permanencia, no un genérico 'gracias por tu preferencia'."
            )
            return info

        # ---------- Pagos reales (Nest Polar / nómina / modo demo) ----------
        if name in ("generar_link_pago", "activar_recaudo_nomina", "verificar_pago",
                   "solicitar_aclaracion"):
            from . import payments
            fn = {"generar_link_pago": payments.generar_link_pago,
                  "activar_recaudo_nomina": payments.activar_recaudo_nomina,
                  "verificar_pago": payments.verificar_pago,
                  "solicitar_aclaracion": payments.solicitar_aclaracion}[name]
            result = fn(conn, session_key, tenant_id, args)
            # WhatsApp opcional del link (mismo patrón KYC/esign): no falla create.
            if name == "generar_link_pago" and isinstance(result, dict):
                checkout_url = result.get("checkout_url")
                if checkout_url:
                    sess = _get_checkout(conn, session_key)
                    real_phone = (sess.get("phone") if sess else None) or (
                        phone if phone and not phone.startswith("web:") else None)
                    if real_phone:
                        try:
                            from . import whatsapp_gateway
                            texto = (
                                "Tequendama Seguros: aquí tienes el link seguro "
                                f"para pagar tu prima ({result.get('concept') or 'seguro'}). "
                                "La tarjeta se digita solo en la pasarela:\n"
                                f"{checkout_url}\n\nRef. {result.get('reference')}"
                            )
                            whatsapp_gateway.enviar_whatsapp(real_phone, texto)
                        except Exception:
                            log.warning(
                                "no se pudo enviar el link de pago por WhatsApp",
                                exc_info=True)
            return result

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

        if name == "crear_campana_marketing":
            if role != "gerente":
                return {"error": "acceso denegado: solo gerentes"}
            from . import marketing_studio
            frase = str(args.get("frase") or "").strip()
            if not frase:
                return {"error": "falta la frase/titular de la campaña"}
            canal = str(args.get("canal") or "instagram_post")
            banner = marketing_studio.generar_banner(
                frase, subtitle=args.get("subtitulo"), cta=args.get("cta"),
                tipo_seguro=args.get("tipo_seguro"), channel=canal)
            if not banner.get("ok"):
                return {"error": banner.get("error") or "no se pudo generar el banner"}
            campaign: dict = {}
            try:
                import requests
                tipo_seguro = str(args.get("tipo_seguro") or "").strip().upper() or None
                resp = requests.post(
                    f"{BACKEND_URL}/api/v1/campaigns",
                    json={"phrase": frase, "subtitle": args.get("subtitulo"),
                          "cta": args.get("cta"), "insuranceType": tipo_seguro,
                          "channel": canal.upper(), "bannerUrl": banner.get("download_url")},
                    timeout=8, headers={"X-Tenant-Id": tenant_id})
                resp.raise_for_status()
                campaign = resp.json() or {}
            except Exception as exc:
                log.warning("no se pudo crear la campaña en el backend: %s", exc)
            return {"ok": True, "demo": banner.get("demo", False),
                    "banner_url": banner.get("download_url"), "campaign": campaign,
                    "mensaje": ("Banner listo" + (" (simulado, falta GEMINI_API_KEY)" if banner.get("demo") else "")
                               + " y campaña creada como borrador. Para enviarla a los leads, "
                                 "confírmalo desde el panel de Campañas — el envío real no se "
                                 "dispara desde este chat.")}

        if name == "solicitar_informe_gerencial":
            if role != "gerente":
                return {"error": "acceso denegado: solo gerentes"}
            email = str(args.get("email") or "").strip()
            if not email:
                return {"error": "falta el correo al que enviar el informe"}
            import asyncio

            from . import reports as reports_mod
            from .email_service import send_email
            html = reports_mod.build_manager_report_html(conn)
            result = asyncio.run(send_email(email, "Reporte gerencial de Tequendama Seguros", html))
            ok = result.get("status") == "sent"
            return {**result, "mensaje": "Informe gerencial enviado por correo." if ok
                    else "No se pudo enviar el informe por correo; avísale al gerente que "
                         "revise la configuración de correo del sistema."}

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
            return {"tipo_detectado": parsed.get("tipo_detectado"),
                    "campos_extraidos": campos, "resumen": parsed.get("resumen")}

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

        if name == "enviar_nota_voz":
            if not phone or phone.startswith("web:"):
                return {"error": "nota de voz no disponible en este canal (solo WhatsApp)"}
            texto = str(args.get("texto") or "").strip()
            if not texto:
                return {"error": "falta el texto de la nota de voz"}
            from . import voice_deepgram, whatsapp_gateway
            from .config import AUDIO_DIR
            audio = voice_deepgram.generar_audio(texto)
            if not audio.get("ok"):
                return {"error": audio.get("error") or "no se pudo generar el audio"}
            filename = audio["audio_url"].rsplit("/", 1)[-1]
            audio_bytes = (AUDIO_DIR / filename).read_bytes()
            if not whatsapp_gateway.enviar_audio(phone, audio_bytes, mimetype="audio/mpeg"):
                return {"error": "no se pudo enviar la nota de voz (gateway de WhatsApp no disponible)"}
            return {"ok": True, "mensaje": "Nota de voz enviada — no la describas, el cliente ya la escuchó."}

        return {"error": f"herramienta desconocida: {name}"}
    finally:
        conn.close()


# ---------- Historial de sesión (PostgreSQL) ----------

def _history_table(conn: psycopg.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS chat_history (
        session_id TEXT, seq INTEGER, message TEXT,
        PRIMARY KEY (session_id, seq))""")


def _load_history(session_id: str, limit: int = 120) -> list[dict]:
    conn = get_conn()
    _history_table(conn)
    rows = conn.execute(
        "SELECT message FROM chat_history WHERE session_id=%s ORDER BY seq DESC LIMIT %s",
        (session_id, limit)).fetchall()
    conn.close()
    msgs = [json.loads(r["message"]) for r in reversed(rows)]
    # La ventana no debe empezar con un 'tool' huérfano ni con un 'assistant' con
    # tool_calls cuyos 'tool' quedaron fuera: la API exige que cada 'tool' siga a su
    # 'assistant'+tool_calls. Recorta el prefijo hasta la primera ancla segura:
    # un 'user', o un 'assistant' YA CERRADO (sin tool_calls) — todo turno normal
    # termina en uno de estos dos, así que un historial largo con muchas
    # tool-calls encadenadas casi nunca degrada a ventana vacía (antes solo
    # 'user' contaba, y una secuencia larga de herramientas podía empujarlo
    # fuera de la ventana sin dejar ningún ancla válida).
    for i, m in enumerate(msgs):
        if m.get("role") == "user" or (m.get("role") == "assistant" and not m.get("tool_calls")):
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
    es_whatsapp = role != "gerente" and not phone.startswith("web:")
    if role == "gerente":
        system = SYSTEM_PROMPT_GERENTE
    else:
        # web: -> Sofía (informativa); número real -> Mónica (WhatsApp, cierra).
        system = SYSTEM_PROMPT_WEB if phone.startswith("web:") else SYSTEM_PROMPT_WHATSAPP
    # Conocimiento del negocio editable por gerencia (panel "Agente IA" del
    # CRM): promos, políticas, aclaraciones de precios. Devuelve "" si no hay
    # entradas o la BD falla — nunca rompe el turno.
    from .knowledge import knowledge_context
    system += knowledge_context(tenant_id)
    # enviar_nota_voz (Deepgram) solo tiene sentido con un número real de
    # WhatsApp al que mandar el audio — Sofía/gerente se quedan con el set base.
    tools = TOOLS_SCHEMA_WHATSAPP if es_whatsapp else TOOLS_SCHEMA

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
                model=DEEPSEEK_MODEL, messages=messages, tools=tools,
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
    _sync_turn_to_docket(role, user_message, reply)
    return {"reply": reply, "quick_replies": quick_replies, "actions": actions,
            "role": role, "documents": documents}


def _sync_turn_to_docket(role: str, user_message: str, reply: str) -> None:
    """Alimenta el motor de versionado/QA (docket, ver app/docket_engine/) con
    el turno real recién ocurrido — fire-and-forget, nunca bloquea ni rompe la
    respuesta al cliente si falla."""
    from .config import DOCKET_ENGINE_ENABLED
    if not DOCKET_ENGINE_ENABLED or not reply:
        return
    try:
        import uuid

        from .docket_engine import store as _docket_store
        campaign_slug = "tequendama-gerente" if role == "gerente" else "tequendama-cliente"
        turns = [{"role": "customer", "text": user_message}, {"role": "agent", "text": reply}]
        transcript = f"Cliente: {user_message}\nTequendama: {reply}"
        c = _docket_store.conn()
        try:
            _docket_store.insert_call(c, campaign_slug, str(uuid.uuid4()), transcript, turns)
            c.commit()
        finally:
            c.close()
    except Exception:
        log.warning("no se pudo sincronizar el turno hacia docket (campaña=%s)", role, exc_info=True)
