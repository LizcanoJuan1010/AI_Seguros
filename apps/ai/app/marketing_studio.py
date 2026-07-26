"""Estudio de banners de marketing (correo / Instagram / LinkedIn) generados
con Gemini (familia "Nano Banana": gemini-3.1-flash-image / gemini-3-pro-image).

Patrón "plantilla + edición" (no una imagen nueva por frase):
  1. Por cada canal se genera UNA plantilla base (colores, layout, estilo,
     espacio reservado para el titular, SIN texto todavía) y se cachea en
     disco (`_template_<channel>.png`).
  2. Cada banner nuevo EDITA esa misma plantilla (misma llamada de Gemini,
     pasándole la plantilla como imagen de entrada) para escribirle encima
     el titular/subtítulo/CTA de esa campaña.
Resultado: todos los banners de un canal comparten el mismo diseño — solo
cambia el texto — en vez de que cada frase produzca un banner con un layout
distinto (los modelos de texto-a-imagen son estocásticos). Se puede forzar
una plantilla nueva con `regenerar_plantilla=True` si el diseño se ve viejo.

Color: en vez de solo describir los hex en texto (el modelo puede
interpretarlos de forma aproximada), se genera un swatch de referencia con
Pillow (colores exactos, sin IA) y se lo pasamos como imagen adjunta — el
mismo patrón de "imagen de referencia para anclar consistencia" que usan las
herramientas de marca existentes (ver research de la sesión).

Sin GEMINI_API_KEY corre en modo demo (mismo criterio que calls.py/Wompi):
no genera nada, degrada limpio con `{"demo": True}`.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .auth import resolve_identity
from .config import (BANNERS_DIR, BRAND_NAME, COLSUBSIDIO_PALETTE, GEMINI_API_KEY,
                     GEMINI_IMAGE_MODEL, PUBLIC_BASE_URL)

log = logging.getLogger("seguria.marketing_studio")
router = APIRouter()

Channel = Literal["instagram_post", "instagram_story", "linkedin", "email"]

# Relación de aspecto por canal (valores soportados por la familia Nano Banana)
# y una descripción legible para el prompt — cada canal tiene un único destino
# de publicación, así que el tamaño no es un parámetro libre.
CHANNEL_SPECS: dict[Channel, dict[str, str]] = {
    "instagram_post": {"aspect_ratio": "1:1", "layout": "publicación cuadrada de feed de Instagram"},
    "instagram_story": {"aspect_ratio": "9:16", "layout": "historia vertical de Instagram"},
    "linkedin": {"aspect_ratio": "16:9", "layout": "imagen de publicación de LinkedIn"},
    "email": {"aspect_ratio": "16:9", "layout": "banner de cabecera de correo (ancho, poco alto visual)"},
}

_FINISHED_OK = {"STOP", "FINISH_REASON_STOP", "1"}


def enabled() -> bool:
    return bool(GEMINI_API_KEY)


def _template_path(channel: Channel) -> Path:
    return BANNERS_DIR / f"_template_{channel}.png"


def _reference_swatch() -> bytes:
    """Imagen de referencia con los colores EXACTOS de Colsubsidio (Pillow,
    sin IA de por medio) — se adjunta al prompt para anclar el color por
    imagen, no solo por descripción en texto de los códigos hex."""
    from PIL import Image, ImageDraw

    p = COLSUBSIDIO_PALETTE
    swatches = [p["azul"], p["amarillo"], p["azul_fondo"], p["gris_texto"], p["blanco"]]
    w = 120
    img = Image.new("RGB", (w * len(swatches), w))
    draw = ImageDraw.Draw(img)
    for i, hexcolor in enumerate(swatches):
        draw.rectangle([i * w, 0, (i + 1) * w, w], fill=hexcolor)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_template_prompt(channel: Channel) -> str:
    spec = CHANNEL_SPECS[channel]
    p = COLSUBSIDIO_PALETTE
    return (
        f"Diseña la PLANTILLA BASE (sin texto todavía) de un banner publicitario para "
        f"{spec['layout']} de {BRAND_NAME}, distribuido por Colsubsidio.\n"
        "- Paleta: usa EXCLUSIVAMENTE los colores de la imagen de referencia adjunta "
        f"(swatch): azul principal {p['azul']}, amarillo de acento {p['amarillo']}, "
        f"azul de fondo suave {p['azul_fondo']}, gris de texto {p['gris_texto']}, "
        f"blanco {p['blanco']}. No inventes otros colores.\n"
        "- Composición: deja un tercio del banner limpio y despejado (sin elementos "
        "encima) reservado para escribir un titular después — indícalo con espacio "
        "negativo, no con un placeholder de texto.\n"
        "- Estilo: corporativo, formas geométricas simples o ilustración plana "
        "relacionada con protección/seguros (escudo, paraguas, familia estilizada), "
        "nada de fotografías de personas reales.\n"
        "- No dibujes ningún logo (ni de Colsubsidio ni de ninguna otra marca) — no "
        "conocemos el logo exacto; usa solo la paleta de color.\n"
        "- No incluyas NINGÚN texto en esta imagen todavía."
    )


def _build_edit_prompt(phrase: str, subtitle: str | None, cta: str | None,
                       tipo_seguro: str | None, channel: Channel) -> str:
    tema = f"seguros de {tipo_seguro}" if tipo_seguro else "protección y seguros"
    lines = [
        "Edita esta plantilla de banner conservando EXACTAMENTE el mismo diseño: "
        "mismos colores, formas, composición y estilo. Solo agrega texto en el "
        "espacio despejado que ya tiene reservado:",
        f'- Titular (grande, bold, muy legible): "{phrase}"',
    ]
    if subtitle:
        lines.append(f'- Subtítulo (más pequeño, debajo del titular): "{subtitle}"')
    if cta:
        lines.append(f'- Etiqueta o botón de llamado a la acción: "{cta}"')
    lines.append(f"- Contexto temático (no lo escribas literal, solo úsalo de guía): {tema}")
    lines.append("No cambies nada más del diseño ya existente de la plantilla.")
    return "\n".join(lines)


def _extract_image(response) -> bytes | None:
    if not response.candidates:
        return None
    content = getattr(response.candidates[0], "content", None)
    for part in getattr(content, "parts", None) or []:
        if getattr(part, "inline_data", None) and part.inline_data.data:
            return part.inline_data.data
    return None


def _block_reason(response) -> str | None:
    """Motivo legible si Gemini bloqueó/no devolvió imagen (moderación),
    en vez de solo reportar 'no hay imagen' sin explicación."""
    fb = getattr(response, "prompt_feedback", None)
    if fb is not None and getattr(fb, "block_reason", None):
        return f"prompt bloqueado: {fb.block_reason}"
    if response.candidates:
        reason = getattr(response.candidates[0], "finish_reason", None)
        if reason is not None and str(reason) not in _FINISHED_OK:
            return f"generación bloqueada: {reason}"
    return None


def _generate_image(client, genai_types, prompt: str, aspect_ratio: str,
                    reference_images: list[bytes] | None = None):
    contents: list = [prompt]
    for img_bytes in reference_images or []:
        contents.append(genai_types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
    return client.models.generate_content(
        model=GEMINI_IMAGE_MODEL,
        contents=contents,
        config=genai_types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=genai_types.ImageConfig(aspect_ratio=aspect_ratio),
        ),
    )


def _get_or_create_template(client, genai_types, channel: Channel, *,
                            force: bool = False) -> bytes:
    path = _template_path(channel)
    if path.exists() and not force:
        return path.read_bytes()

    prompt = _build_template_prompt(channel)
    response = _generate_image(client, genai_types, prompt,
                               CHANNEL_SPECS[channel]["aspect_ratio"],
                               reference_images=[_reference_swatch()])
    image_bytes = _extract_image(response)
    if not image_bytes:
        raise RuntimeError(_block_reason(response) or "Gemini no devolvió la plantilla base")
    path.write_bytes(image_bytes)
    log.info("plantilla base (re)generada para canal=%s", channel)
    return image_bytes


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "banner"


def generar_banner(phrase: str, *, subtitle: str | None = None, cta: str | None = None,
                   tipo_seguro: str | None = None, channel: Channel = "instagram_post",
                   regenerar_plantilla: bool = False) -> dict[str, Any]:
    """Genera (o edita la plantilla existente de) un banner de campaña y lo
    guarda en `BANNERS_DIR`. Devuelve `{"ok": True, "demo": True, ...}` sin
    GEMINI_API_KEY configurada (no rompe el flujo de quien lo llame)."""
    if channel not in CHANNEL_SPECS:
        return {"ok": False, "error": f"canal inválido: {channel}. Usa uno de {list(CHANNEL_SPECS)}"}
    if not phrase or not phrase.strip():
        return {"ok": False, "error": "la frase del banner no puede estar vacía"}

    if not enabled():
        log.info("modo demo: no se genera banner real (falta GEMINI_API_KEY)")
        return {"ok": True, "demo": True, "file_path": None, "download_url": None,
                "mensaje": "Banner simulado (falta GEMINI_API_KEY)."}

    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=GEMINI_API_KEY)
        template_bytes = _get_or_create_template(client, genai_types, channel,
                                                 force=regenerar_plantilla)

        edit_prompt = _build_edit_prompt(phrase, subtitle, cta, tipo_seguro, channel)
        response = _generate_image(client, genai_types, edit_prompt,
                                   CHANNEL_SPECS[channel]["aspect_ratio"],
                                   reference_images=[template_bytes])
        image_bytes = _extract_image(response)
        if not image_bytes:
            return {"ok": False, "demo": False,
                    "error": _block_reason(response) or "Gemini no devolvió una imagen"}

        filename = f"banner_{channel}_{_slug(phrase)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = BANNERS_DIR / filename
        path.write_bytes(image_bytes)
        log.info("banner generado: %s (canal=%s)", filename, channel)
        # Absoluta si PUBLIC_BASE_URL está configurada (necesaria para poder
        # mandarla como link en un mensaje de WhatsApp de campaña — ver
        # campaign_broadcast.py); si no, relativa como siempre (rutas del SPA).
        download_url = f"{PUBLIC_BASE_URL}/api/marketing/banners/{filename}" if PUBLIC_BASE_URL \
            else f"/api/marketing/banners/{filename}"
        return {"ok": True, "demo": False, "file_path": str(path),
                "download_url": download_url,
                "channel": channel, "aspect_ratio": CHANNEL_SPECS[channel]["aspect_ratio"]}
    except Exception as exc:
        log.warning("no se pudo generar el banner: %s", exc)
        return {"ok": False, "demo": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Router: POST /api/marketing/banner + GET /api/marketing/banners/{filename}
# (módulo autocontenido, mismo patrón que assistant.py/embedded.py — main.py
# solo hace app.include_router(marketing_studio.router))
# ---------------------------------------------------------------------------

def _require_manager(authorization: str = Header(default=""),
                     x_tenant_id: str = Header(default="", alias="X-Tenant-Id"),
                     x_api_key: str = Header(default="")) -> None:
    """Gerente real (JWT del login, igual que ya respeta el chat en
    agent_core.py — ver `role == "gerente"`) O el X-API-Key estático como
    fallback de servicio/pruebas (mismo `resolve_identity` que usa /api/chat,
    con x_api_key en el rol de `manager_key`)."""
    _, role = resolve_identity(authorization, x_tenant_id, x_api_key)
    if role != "gerente":
        raise HTTPException(403, "Se requiere sesión de gerente (JWT) o X-API-Key de gerente")


class BannerRequest(BaseModel):
    phrase: str = Field(..., description="Titular del banner (se renderiza sobre la imagen)")
    subtitle: str | None = Field(None, description="Texto secundario, opcional")
    cta: str | None = Field(None, description="Llamado a la acción, ej. 'Cotiza ahora'")
    tipo_seguro: str | None = Field(None, description="vida|auto|salud|hogar|viaje... (contexto temático)")
    channel: str = Field("instagram_post",
                         description="instagram_post|instagram_story|linkedin|email")
    regenerar_plantilla: bool = Field(
        False, description="Fuerza un diseño base nuevo para el canal en vez de "
                           "reusar la plantilla ya cacheada (úsalo si el diseño se ve viejo)")


@router.post("/api/marketing/banner", dependencies=[Depends(_require_manager)])
def create_banner(req: BannerRequest) -> dict:
    """Genera un banner de campaña (Gemini) en la paleta de Colsubsidio, listo
    para adjuntar a un correo o publicar en Instagram/LinkedIn. Reusa la misma
    plantilla base por canal (mismo diseño) y solo le edita el texto — así
    todos los banners de una campaña se ven consistentes."""
    out = generar_banner(req.phrase, subtitle=req.subtitle, cta=req.cta,
                         tipo_seguro=req.tipo_seguro, channel=req.channel,
                         regenerar_plantilla=req.regenerar_plantilla)
    if not out.get("ok"):
        raise HTTPException(400, out.get("error", "no se pudo generar el banner"))
    return out


@router.get("/api/marketing/banners/{filename}")
def download_banner(filename: str) -> FileResponse:
    path = (BANNERS_DIR / filename).resolve()
    if not path.is_file() or path.parent != BANNERS_DIR.resolve():
        raise HTTPException(404, "Banner no encontrado")
    return FileResponse(path, media_type="image/png", filename=filename)
