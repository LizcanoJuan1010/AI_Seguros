"""
Configuración del agente de voz — personalidad, capacidades y audio.

Adaptado del reference implementation de Deepgram (homeowners insurance, en
inglés) a Tequendama Seguros (seguro de vehículo, español colombiano).

Configura la Voice Agent API de Deepgram con:
  - Encoding de audio (mulaw 8kHz, compatible con Twilio)
  - Speech-to-text: nova-3 (v1), NO Flux (v2) — Flux es solo inglés
    (`flux-general-en`, sin campo `language`); nova-3 sí acepta `language`.
  - LLM (configurable, default gpt-4o-mini)
  - Text-to-speech (Deepgram Aura-2, voz en español — ver VOICE_MODEL)
  - System prompt (agente de seguimiento de leads de seguro de vehículo)
  - Funciones (check_availability, book_appointment, update_lead, end_call)

El system prompt se arma dinámicamente con los datos del lead inyectados
desde el POST /make-call. Para cambiar el LLM/voz/STT, edita LLM_MODEL /
VOICE_MODEL / STT_MODEL / STT_LANGUAGE en tu .env.
"""
from datetime import date

from config import VOICE_MODEL, LLM_MODEL, LLM_PROVIDER, TTS_PROVIDER, STT_MODEL, STT_LANGUAGE
from deepgram.agent.v1 import (
    AgentV1Settings,
    AgentV1SettingsAudio,
    AgentV1SettingsAudioInput,
    AgentV1SettingsAudioOutput,
    AgentV1SettingsAgent,
    AgentV1SettingsAgentListen,
    AgentV1SettingsAgentListenProvider_V1,
)
from deepgram.types.think_settings_v1 import ThinkSettingsV1
from deepgram.types.think_settings_v1provider import (
    ThinkSettingsV1Provider_OpenAi,
    ThinkSettingsV1Provider_Anthropic,
    ThinkSettingsV1Provider_Google,
)
from deepgram.types.think_settings_v1functions_item import ThinkSettingsV1FunctionsItem
from deepgram.types.speak_settings_v1 import SpeakSettingsV1
from deepgram.types.speak_settings_v1provider import SpeakSettingsV1Provider_Deepgram


# ---------------------------------------------------------------------------
# Provider class lookup
# ---------------------------------------------------------------------------
_THINK_PROVIDERS = {
    "open_ai": ThinkSettingsV1Provider_OpenAi,
    "anthropic": ThinkSettingsV1Provider_Anthropic,
    "google": ThinkSettingsV1Provider_Google,
}

_SPEAK_PROVIDERS = {
    "deepgram": SpeakSettingsV1Provider_Deepgram,
}


# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------
# This prompt follows voice-specific best practices from docs/PROMPT_GUIDE.md.
# Lead context is injected at call time via string formatting.

_DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fecha_es(d: date) -> str:
    """Formatea la fecha en español sin depender del locale del sistema
    (python:3.12-slim no trae es_CO/es_ES instalado por defecto —
    strftime('%A'/'%B') devolvería nombres en inglés)."""
    return f"{_DIAS_ES[d.weekday()]} {d.day} de {_MESES_ES[d.month - 1]} de {d.year}"


_TODAY = date.today()
_TODAY_STR = _fecha_es(_TODAY)  # ej. "lunes 24 de julio de 2026"


def _build_system_prompt(lead_context: dict) -> str:
    """Arma el system prompt con los datos del lead inyectados.

    Args:
        lead_context: dict con los campos del lead (first_name, last_name,
                      vehicle, current_insurance_status, etc.)
    """
    vehicle = lead_context.get("vehicle", {})
    vehicle_str = f"{vehicle.get('brand', '')} {vehicle.get('model', '')} {vehicle.get('year', '')}".strip()
    city = vehicle.get("city", "")

    status = lead_context.get("current_insurance_status", "unknown")
    status_context = {
        "switching": "actualmente asegurado pero buscando cambiar de aseguradora",
        "first_time_buyer": "asegurando su vehículo por primera vez",
        "lapsed": "tenía una póliza que ya venció",
    }.get(status, "buscando seguro para su vehículo")

    first_name = lead_context.get('first_name', '')
    last_name = lead_context.get('last_name', '')
    full_name = f"{first_name} {last_name}".strip()

    return f"""Eres Dora, asesora digital de seguros de Tequendama Seguros, llamando en nombre de la empresa para dar seguimiento a una solicitud de cotización de seguro de vehículo. Hablas español colombiano, cálido y profesional.

FECHA DE HOY: {_TODAY_STR}

REGLAS DE FORMATO DE VOZ:
Eres un agente de VOZ. Tus respuestas se leen en voz alta por texto-a-voz.
- Usa solo lenguaje conversacional plano
- NADA de markdown, emojis, corchetes ni formato especial
- Respuestas breves: 1-2 frases por turno
- Di los números de forma natural, no como dígitos sueltos
- Para leer números como placas o teléfonos, sepáralos con puntos al hablar: "3. 2. 0."
- Di fechas y horas de forma natural ("el jueves a las dos de la tarde", no "2026-03-05T14:00")
- NUNCA anuncies ni narres las llamadas a herramientas. No digas "déjame revisar", "un momento mientras busco" ni nada similar. Presenta el resultado directamente cuando llegue.

REGLAS DE CUMPLIMIENTO (obligatorias):
1. DEBES revelar que eres un asistente automático al inicio de la llamada
2. DEBES aclarar que NO eres una asesora licenciada y que no puedes vender, asesorar ni comprometer ningún producto de seguro
3. NO DEBES dar precios exactos ni recomendar coberturas específicas
4. Si la persona quiere terminar la llamada, déjala ir de inmediato — sin insistir, sin venta forzada

CONTEXTO DEL LEAD (de su solicitud de cotización):
- Nombre: {full_name}
- Teléfono: {lead_context.get('phone', '')}
- Email: {lead_context.get('email', '')}
- Vehículo: {vehicle_str or 'no especificado'}
- Ciudad: {city or 'no especificada'}
- Situación de aseguramiento: {status_context}
- Inicio de cobertura deseado: {lead_context.get('desired_coverage_start', 'no especificado')}
- Cotización enviada: {lead_context.get('quote_submitted_at', 'recientemente')}

FLUJO DE LA LLAMADA:
Sigue estas etapas en orden. Sé conversacional, no robótica.

1. APERTURA (obligatoria):
   Tu saludo preguntará "¿Hablo con {full_name}?"
   Espera la respuesta antes de continuar.

   Si SÍ (confirma que es {first_name}):
   - Explica brevemente que llamas por su solicitud de cotización de seguro de vehículo
   - Aclara que no eres una asesora licenciada
   - Explica el propósito: verificar unos datos de su cotización y, si le interesa, agendar una consulta telefónica con un asesor licenciado
   - Pregunta si tiene unos minutos

   Si NO (persona equivocada):
   - Discúlpate por la confusión
   - Pregunta si sabe cuándo podría encontrar a {first_name}
   - Si te dan un horario, anótalo y llama a update_lead con callback_requested
   - Si no saben o piden que no vuelvas a llamar, termina la llamada con cortesía
   - Llama a end_call

   Si dicen que están ocupados o piden que llames después: pregunta cuándo sería mejor, anótalo en update_lead con callback_requested, y llama a end_call.

2. VERIFICAR INFORMACIÓN ENVIADA:
   Confirma los datos clave de su cotización. Agrúpalos de forma natural:
   - Vehículo (marca, modelo, año) y ciudad
   - Fecha deseada de inicio de cobertura
   Por ejemplo: "Tengo aquí que buscas cobertura para tu {vehicle_str or '[vehículo]'} en {city or '[ciudad]'}, con inicio aproximado el {lead_context.get('desired_coverage_start', '[fecha]')}. ¿Está correcto?"

3. RECOLECTAR INFORMACIÓN ADICIONAL:
   Haz estas preguntas UNA A LA VEZ. Pregunta una, espera la respuesta, luego la siguiente.
   NO combines varias preguntas en un mismo turno.

   Pregunta 1: "¿Tu vehículo lo usas principalmente particular o para trabajo, como aplicaciones de transporte?"
   [ESPERA la respuesta]

   Pregunta 2: "¿Has tenido algún siniestro o reclamo de seguro en los últimos cinco años?"
   [ESPERA la respuesta]

   Si no sabe una respuesta, está bien — anótala como desconocida y sigue adelante.

4. AGENDAR CONSULTA:
   - Primero pregunta: "¿Tienes preferencia por mañana o tarde para la consulta?"
   - Luego llama a check_availability para obtener los horarios disponibles
   - Presenta 2-3 opciones que coincidan con su preferencia (o las mejores disponibles si no tiene preferencia)
   - Antes de agendar, confirma su elección: repite el horario y pregunta "¿Confirmo esa cita?"
   - SOLO después de que confirme, llama a book_appointment

5. CIERRE:
   - Confirma la cita una última vez
   - Llama a update_lead con el resumen completo de la llamada
   - Di UNA sola despedida corta (ej. "Muchas gracias, que tengas un buen día")
   - NO te repitas. Una vez te despediste, terminaste. No digas más despedidas.
   - Llama a end_call

REGLAS DE LLAMADAS A FUNCIONES:
- check_availability: llama a esto para obtener horarios disponibles. No necesita confirmación, es de solo lectura. NO narres la búsqueda — presenta el resultado directamente.
- book_appointment: llama DESPUÉS de que la persona confirme explícitamente un horario. Repite su elección y obtén un "sí" antes de llamarla.
- update_lead: llama al FINAL de cada llamada, sin importar el resultado. Incluye call_outcome, disposition y un call_summary en lenguaje natural.
- end_call: llama cuando la conversación terminó. Despídete PRIMERO, luego llama a la función.

IMPORTANTE — EVITA REPETIRTE:
- Nunca repitas información que ya dijiste
- Si ya confirmaste los detalles de la cita, no los repitas
- Si ya te despediste, no te despidas de nuevo
- Cada respuesta debe sumar información nueva o avanzar la conversación

CRITERIOS DE DISPOSICIÓN:
- qualified: todo en orden. Seguimiento estándar.
- qualified_with_concerns: viable pero surgió algo notable (varios siniestros, factores de riesgo notables). Anota las inquietudes en call_summary.
- not_viable: EXTREMADAMENTE raro. Solo para casos obvios (vendió el vehículo, la persona no es la dueña). Por defecto usa qualified_with_concerns en vez de esto.

ESTILO DE CONVERSACIÓN:
- Profesional, directa y eficiente. Ni excesivamente efusiva ni fría.
- Esto debería tomar 2-4 minutos en total
- Haz las preguntas de forma natural, no como un checklist
- Si se van del tema, redirige con suavidad
- Nunca presiones — estás para ayudar, no para vender a la fuerza
- NO uses signos de exclamación. Mantén un tono calmado y parejo.
- NO digas cosas como "¡Excelente elección!", "¡Genial!", "¡Perfecto!" ni relleno similar. Simplemente avanza. Si necesitas reconocer algo, un simple "listo" o "ok" basta.
"""


def _build_greeting(lead_context: dict) -> str:
    """Saludo inicial que confirma la identidad antes de continuar."""
    first_name = lead_context.get("first_name", "")
    last_name = lead_context.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip() or "buenas"
    return (
        f"Hola, te habla un asistente automático de Tequendama Seguros. "
        f"¿Hablo con {full_name}?"
    )


# ---------------------------------------------------------------------------
# Function definitions
# ---------------------------------------------------------------------------
# Each function maps to a method in backend/lead_service.py.
# See docs/FUNCTION_GUIDE.md for definition best practices.

FUNCTIONS = [
    ThinkSettingsV1FunctionsItem(
        name="check_availability",
        description="""Consulta los horarios disponibles de consulta con asesores licenciados de seguros.

Llama a esto cuando estés lista para agendar una consulta para el lead. Devuelve fechas/horas disponibles con nombre del asesor.

Es de solo lectura — no necesita confirmación antes de llamarla.""",
        parameters={
            "type": "object",
            "properties": {
                "lead_id": {
                    "type": "string",
                    "description": "El lead ID del contexto del lead"
                },
                "timezone": {
                    "type": "string",
                    "description": "Zona horaria del lead (ej. 'America/Bogota'). Asume 'America/Bogota' si no se indica otra."
                }
            },
            "required": ["lead_id"]
        }
    ),
    ThinkSettingsV1FunctionsItem(
        name="book_appointment",
        description="""Agenda un horario de consulta con un asesor licenciado de seguros.

IMPORTANTE: Antes de llamar esta función, DEBES:
1. Llamar check_availability para obtener horarios disponibles
2. Presentar 2-3 opciones a la persona
3. ESPERAR a que elija un horario
4. LUEGO llamar esta función con el horario elegido

Solo llama esto después de que la persona haya elegido un horario específico.""",
        parameters={
            "type": "object",
            "properties": {
                "lead_id": {
                    "type": "string",
                    "description": "El lead ID del contexto del lead"
                },
                "selected_slot": {
                    "type": "string",
                    "description": "La fecha/hora del horario elegido (formato ISO 8601 de los resultados de check_availability)"
                },
                "agent_name": {
                    "type": "string",
                    "description": "El nombre del asesor licenciado para el horario elegido"
                }
            },
            "required": ["lead_id", "selected_slot", "agent_name"]
        }
    ),
    ThinkSettingsV1FunctionsItem(
        name="update_lead",
        description="""Registra el resultado de la llamada, la disposición y la información recolectada. Llama a esto al FINAL de cada llamada, sin importar el resultado.

Este es el registro final de la llamada. Incluye todo lo relevante: qué se verificó, qué información nueva se recolectó, la evaluación de disposición, y un resumen en lenguaje natural que un asesor humano pueda leer.

Valores de call_outcome: appointment_scheduled, callback_requested, not_interested, not_viable, no_answer_voicemail_left
Valores de disposition: qualified, qualified_with_concerns, not_viable""",
        parameters={
            "type": "object",
            "properties": {
                "lead_id": {
                    "type": "string",
                    "description": "El lead ID"
                },
                "call_outcome": {
                    "type": "string",
                    "description": "El resultado de la llamada",
                    "enum": ["appointment_scheduled", "callback_requested", "not_interested", "not_viable"]
                },
                "disposition": {
                    "type": "string",
                    "description": "Disposición de calificación del lead",
                    "enum": ["qualified", "qualified_with_concerns", "not_viable"]
                },
                "appointment_id": {
                    "type": "string",
                    "description": "El ID de confirmación de book_appointment, si se agendó una cita"
                },
                "verified_info": {
                    "type": "object",
                    "description": "Qué información enviada se verificó (ej. vehicle_confirmed, city_confirmed, coverage_start_confirmed)"
                },
                "new_info_gathered": {
                    "type": "object",
                    "description": "Información nueva recolectada durante la llamada (ej. uso_particular_o_trabajo, siniestros_ultimos_5_anos)"
                },
                "call_summary": {
                    "type": "string",
                    "description": "Resumen en lenguaje natural de la llamada que un asesor licenciado pueda leer antes de su consulta"
                }
            },
            "required": ["lead_id", "call_outcome", "disposition", "call_summary"]
        }
    ),
    ThinkSettingsV1FunctionsItem(
        name="end_call",
        description="""Termina la llamada telefónica con cortesía.

Llama a esto después de:
- Haber llamado a update_lead con el resultado de la llamada
- Haberte despedido
- Que la conversación haya concluido naturalmente

Despídete PRIMERO, luego llama a esta función. No generes texto después de llamarla.""",
        parameters={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Por qué termina la llamada",
                    "enum": ["appointment_booked", "callback_requested", "not_interested", "not_viable"]
                }
            },
            "required": ["reason"]
        }
    ),
]


# ---------------------------------------------------------------------------
# Build the settings message
# ---------------------------------------------------------------------------

def get_agent_config(lead_context: dict) -> AgentV1Settings:
    """Build the Voice Agent settings message for Deepgram.

    This is sent once per call when the Deepgram connection is established.
    It configures STT, LLM, TTS, and the agent's prompt and tools.

    Args:
        lead_context: Dict with lead fields injected into the system prompt.
    """
    think_provider_cls = _THINK_PROVIDERS.get(LLM_PROVIDER, ThinkSettingsV1Provider_OpenAi)
    speak_provider_cls = _SPEAK_PROVIDERS.get(TTS_PROVIDER, SpeakSettingsV1Provider_Deepgram)

    return AgentV1Settings(
        type="Settings",
        audio=AgentV1SettingsAudio(
            input=AgentV1SettingsAudioInput(
                encoding="mulaw",
                sample_rate=8000,
            ),
            output=AgentV1SettingsAudioOutput(
                encoding="mulaw",
                sample_rate=8000,
                container="none",
            ),
        ),
        agent=AgentV1SettingsAgent(
            # v1 (nova-3), NO v2/Flux: Flux es solo inglés (sin campo
            # `language`); nova-3 sí lo acepta — necesario para español.
            listen=AgentV1SettingsAgentListen(
                provider=AgentV1SettingsAgentListenProvider_V1(
                    version="v1",
                    type="deepgram",
                    model=STT_MODEL,
                    language=STT_LANGUAGE,
                ),
            ),
            think=ThinkSettingsV1(
                provider=think_provider_cls(
                    type=LLM_PROVIDER,
                    model=LLM_MODEL,
                ),
                prompt=_build_system_prompt(lead_context),
                functions=FUNCTIONS,
            ),
            speak=SpeakSettingsV1(
                provider=speak_provider_cls(
                    type=TTS_PROVIDER,
                    model=VOICE_MODEL,
                ),
            ),
            greeting=_build_greeting(lead_context),
        ),
    )
