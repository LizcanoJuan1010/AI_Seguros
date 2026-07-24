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
