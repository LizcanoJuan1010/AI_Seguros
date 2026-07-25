"""Cliente de salida hacia el gateway Baileys de WhatsApp — el MISMO proceso
multi-tenant ya desplegado (Railway) que usa Diache, con Tequendama como un
tenant nuevo (`WA_GATEWAY_TENANT`). No desplegamos ni pareamos un WhatsApp
propio: reusamos la infraestructura ya corriendo (ver plan de esta sesión).

Mismo patrón de degradación limpia que `calls.py`/pagos: sin `WA_GATEWAY_URL`
configurada, o si el gateway no responde, no rompe el turno — la respuesta ya
quedó registrada en el CRM aunque no llegue el WhatsApp.
"""
import logging

import requests

from .config import WA_GATEWAY_TENANT, WA_GATEWAY_URL, WA_GATEWAY_WEBHOOK_SECRET

log = logging.getLogger("seguria.whatsapp_gateway")

_TIMEOUT = 15


def enabled() -> bool:
    return bool(WA_GATEWAY_URL and WA_GATEWAY_WEBHOOK_SECRET)


def enviar_whatsapp(phone: str, text: str) -> bool:
    """Envía `text` por WhatsApp a `phone` vía `POST {WA_GATEWAY_URL}/send`.
    `phone` puede venir con o sin '+'; el gateway espera solo dígitos."""
    if not enabled():
        log.info("WA_GATEWAY no configurado: no se envía WhatsApp a %s (demo)", phone)
        return False
    digits = phone.lstrip("+")
    try:
        resp = requests.post(
            f"{WA_GATEWAY_URL}/send",
            json={"tenant": WA_GATEWAY_TENANT, "to": digits, "text": text},
            timeout=_TIMEOUT,
            headers={"x-webhook-secret": WA_GATEWAY_WEBHOOK_SECRET},
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        log.warning("no se pudo enviar WhatsApp a %s: %s", phone, exc)
        return False


def _sintetizar(text: str) -> bytes | None:
    """MP3 del texto vía Kokoro-FastAPI (el mismo TTS que ya usa el chat web
    en `/api/assistant/tts`, perfil `voz` del compose). None si el servicio
    no responde — nunca rompe el turno."""
    from .config import TTS_URL, TTS_VOICE
    try:
        resp = requests.post(
            f"{TTS_URL}/v1/audio/speech",
            json={"model": "kokoro", "voice": TTS_VOICE, "input": text[:600],
                 "response_format": "mp3"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        log.info("TTS no disponible para nota de voz (%s): %s", text[:40], exc)
        return None


def enviar_audio(phone: str, audio: bytes, mimetype: str = "audio/mpeg") -> bool:
    """Envía un buffer de audio YA SINTETIZADO (no importa si vino de Kokoro
    o de Deepgram) como nota de voz por WhatsApp vía `POST
    {WA_GATEWAY_URL}/send-audio` (base64). El endpoint vive en
    `apps/services/baileys-bridge/index.js` (`ptt: true`, transcodifica a
    ogg/opus con ffmpeg). Degrada limpio a False (nunca rompe el turno) si
    el gateway no responde."""
    if not enabled():
        log.info("WA_GATEWAY no configurado: no se envía nota de voz a %s (demo)", phone)
        return False
    import base64
    digits = phone.lstrip("+")
    try:
        resp = requests.post(
            f"{WA_GATEWAY_URL}/send-audio",
            json={"tenant": WA_GATEWAY_TENANT, "to": digits,
                 "audio_base64": base64.b64encode(audio).decode(), "mimetype": mimetype},
            timeout=_TIMEOUT,
            headers={"x-webhook-secret": WA_GATEWAY_WEBHOOK_SECRET},
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        log.info("no se pudo enviar la nota de voz a %s: %s", phone, exc)
        return False


def enviar_nota_voz(phone: str, text: str) -> bool:
    """Sintetiza `text` con Kokoro (nota de voz corta y determinista — ver
    `_EDUCACION_VOZ` en main.py, dispara sola tras ciertas tools sensibles)
    y la envía. Para que el AGENTE elija responder con voz como parte de la
    conversación (Deepgram, más natural), ver la tool `enviar_nota_voz` en
    `agent_core.py`, que llama a `enviar_audio` directo."""
    if not enabled():
        log.info("WA_GATEWAY no configurado: no se envía nota de voz a %s (demo)", phone)
        return False
    audio = _sintetizar(text)
    if audio is None:
        return False
    return enviar_audio(phone, audio, mimetype="audio/mpeg")
