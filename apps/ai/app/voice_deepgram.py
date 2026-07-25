"""Voz vía Deepgram — dos tools independientes (transcribir/generar), cada
uno devuelve un JSON plano para que Hermes (u otro llamador) los invoque
como cualquier otro endpoint de la API (ver AGENTS.md, mismo patrón que
`/api/quotes`/`/api/roles`). Mismo proveedor y mismo catálogo de modelos que
`apps/services/deepgram-outbound` (nova-3/es para STT, aura-2-celeste-es
para TTS) — no es el motor de llamadas salientes (eso ya vive aparte), esto
es la parte de audio de las notas de voz (WhatsApp/chat).

Endpoints REST verificados contra la doc vigente de Deepgram (no inventados):
  STT: POST https://api.deepgram.com/v1/listen
  TTS: POST https://api.deepgram.com/v1/speak
Ambos con header `Authorization: Token <DEEPGRAM_API_KEY>`.

Sin DEEPGRAM_API_KEY corre en modo demo (mismo criterio que el resto del
stack): no llama a nadie, degrada limpio con un error explícito en el JSON
en vez de romper el flujo de quien lo invoque.
"""
import logging
import uuid

import requests

from .config import (AUDIO_DIR, DEEPGRAM_API_KEY, DEEPGRAM_STT_LANGUAGE,
                     DEEPGRAM_STT_MODEL, DEEPGRAM_VOICE_MODEL)

log = logging.getLogger("seguria.voice_deepgram")

_TIMEOUT = 30


def enabled() -> bool:
    return bool(DEEPGRAM_API_KEY)


def transcribir(*, audio_bytes: bytes | None = None, content_type: str = "audio/ogg",
               audio_url: str | None = None) -> dict:
    """STT: nota de voz -> texto. Pasa `audio_bytes` (+ `content_type`) para un
    archivo ya descargado, o `audio_url` si Deepgram puede bajarlo directo.
    Devuelve siempre un dict JSON-serializable, nunca lanza excepción."""
    if not enabled():
        return {"ok": False, "demo": True, "texto": "",
                "error": "DEEPGRAM_API_KEY no configurada (modo demo)"}
    if not audio_bytes and not audio_url:
        return {"ok": False, "demo": False, "texto": "", "error": "falta audio_bytes o audio_url"}

    params = {"model": DEEPGRAM_STT_MODEL, "language": DEEPGRAM_STT_LANGUAGE,
             "punctuate": "true", "smart_format": "true"}
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
    try:
        if audio_url:
            headers["Content-Type"] = "application/json"
            resp = requests.post("https://api.deepgram.com/v1/listen", params=params,
                                 headers=headers, json={"url": audio_url}, timeout=_TIMEOUT)
        else:
            headers["Content-Type"] = content_type
            resp = requests.post("https://api.deepgram.com/v1/listen", params=params,
                                 headers=headers, data=audio_bytes, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        texto = (data.get("results", {}).get("channels", [{}])[0]
                .get("alternatives", [{}])[0].get("transcript", ""))
        return {"ok": True, "demo": False, "texto": texto, "idioma": DEEPGRAM_STT_LANGUAGE}
    except Exception as exc:
        log.warning("no se pudo transcribir con Deepgram: %s", exc)
        return {"ok": False, "demo": False, "texto": "", "error": str(exc)}


def generar_audio(texto: str) -> dict:
    """TTS: texto -> nota de voz (mp3, guardado en AUDIO_DIR). Devuelve
    {"ok", "audio_url"} — el archivo se sirve luego vía GET /api/voice/audio/{name}.
    Nunca lanza excepción."""
    if not enabled():
        return {"ok": False, "demo": True, "audio_url": None,
                "error": "DEEPGRAM_API_KEY no configurada (modo demo)"}
    if not texto or not texto.strip():
        return {"ok": False, "demo": False, "audio_url": None, "error": "falta texto"}

    try:
        resp = requests.post(
            "https://api.deepgram.com/v1/speak",
            params={"model": DEEPGRAM_VOICE_MODEL},
            headers={"Authorization": f"Token {DEEPGRAM_API_KEY}", "Content-Type": "application/json"},
            json={"text": texto}, timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        filename = f"voz_{uuid.uuid4().hex[:12]}.mp3"
        (AUDIO_DIR / filename).write_bytes(resp.content)
        return {"ok": True, "demo": False, "audio_url": f"/api/voice/audio/{filename}"}
    except Exception as exc:
        log.warning("no se pudo generar audio con Deepgram: %s", exc)
        return {"ok": False, "demo": False, "audio_url": None, "error": str(exc)}
