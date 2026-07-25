"""Base 04 (siembra) — puerto de `seed_versions.py` de docket-motor.

Siembra los prompts actuales de las 3 identidades cliente-facing que viven en
código (`agent_core.SYSTEM_PROMPT_WEB_DEFAULT`/`_WHATSAPP_DEFAULT`/
`_GERENTE_DEFAULT` — Sofía, Camilo y el analista gerencial; Martín, la llamada
saliente, vive aparte en `apps/ai/app/reference/elevenlabs_agent_prompt.md`,
fuera de este motor) como `version_number=1, source='seed'`, una campaña por
identidad. Idempotente — no reinserta si la v1 ya existe. Importa
`agent_core` de forma perezosa (dentro de la función, no a nivel de módulo)
para evitar un import circular: `agent_core` lee de vuelta
`docket_engine.store`, no `docket_engine.seed`.
"""
import logging

from . import store

log = logging.getLogger("seguria.docket_engine.seed")

CAMPAIGNS = ("tequendama-cliente", "tequendama-whatsapp", "tequendama-gerente")


def _default_prompt(client_slug: str) -> str:
    from .. import agent_core
    if client_slug == "tequendama-gerente":
        return agent_core.SYSTEM_PROMPT_GERENTE_DEFAULT
    if client_slug == "tequendama-whatsapp":
        return agent_core.SYSTEM_PROMPT_WHATSAPP_DEFAULT
    return agent_core.SYSTEM_PROMPT_WEB_DEFAULT


def run_all() -> dict[str, str]:
    """Devuelve {client_slug: 'creada' | 'ya existía'}."""
    c = store.conn()
    try:
        results = {}
        for slug in CAMPAIGNS:
            campaign_id = store.get_or_create_campaign(c, slug)
            existing = c.execute(
                "SELECT id FROM docket.versions WHERE campaign_id = %s AND version_number = 1",
                (campaign_id,)).fetchone()
            if existing:
                results[slug] = "ya existía"
                continue
            c.execute(
                """INSERT INTO docket.versions (campaign_id, version_number, prompt_text, source)
                   VALUES (%s, 1, %s, 'seed')""",
                (campaign_id, _default_prompt(slug)))
            results[slug] = "creada"
            log.info("docket seed %s: v1 creada", slug)
        c.commit()
        return results
    finally:
        c.close()
