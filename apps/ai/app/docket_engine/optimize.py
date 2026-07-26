"""Base 05 (GEPA) — puerto de docket-motor a `docket.*`/DeepSeek.

Para una campaña: toma la mejor versión (mayor puntaje promedio), reflexiona
sobre sus clusters peor puntuados y escribe EXACTAMENTE una versión nueva
(`source='gepa'`). No hace loop — cuántas rondas correr es una decisión
humana (se dispara vía `POST /api/docket/recompute`), no de este módulo.
"""
import logging

from ..config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from . import store

log = logging.getLogger("seguria.docket_engine.optimize")

FAILURE_TRACE_COUNT = 5


def _client():
    from openai import OpenAI
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=90.0, max_retries=2)


def best_version(c, campaign_id: str) -> dict | None:
    versions = c.execute(
        "SELECT id, version_number, prompt_text FROM docket.versions WHERE campaign_id = %s",
        (campaign_id,)).fetchall()
    if not versions:
        return None
    scored = []
    for version in versions:
        rows = c.execute(
            "SELECT score FROM docket.scores WHERE version_id = %s", (version["id"],)).fetchall()
        if rows:
            mean_score = sum(r["score"] for r in rows) / len(rows)
            scored.append((mean_score, version))
    if not scored:
        return None
    return max(scored, key=lambda pair: pair[0])[1]


def worst_clusters(c, version_id: str, limit: int) -> list[dict]:
    rows = c.execute(
        "SELECT cluster_id, score, criterion, notes FROM docket.scores WHERE version_id = %s",
        (version_id,)).fetchall()
    by_cluster: dict[str, list[dict]] = {}
    for row in rows:
        by_cluster.setdefault(row["cluster_id"], []).append(row)
    ranked = sorted(
        by_cluster.items(),
        key=lambda pair: sum(r["score"] for r in pair[1]) / len(pair[1]))[:limit]
    traces = []
    for cluster_id, cluster_scores in ranked:
        cluster = c.execute(
            "SELECT representative_text FROM docket.clusters WHERE id = %s", (cluster_id,)).fetchone()
        traces.append({"representative_text": cluster["representative_text"], "scores": cluster_scores})
    return traces


def reflect_and_rewrite(llm, prompt_text: str, traces: list[dict]) -> str:
    traces_desc = "\n\n".join(
        f"El cliente dijo: {t['representative_text']}\n"
        + "\n".join(f"  {s['criterion']}: {s['score']}/5 — {s.get('notes', '')}" for s in t["scores"])
        for t in traces)
    reflection_prompt = f"""Estás mejorando el prompt de sistema de un agente conversacional con
reflexión estilo GEPA: diagnostica por qué falló en entradas concretas de
clientes, y reescribe el prompt para corregir eso, preservando todo lo que
ya funciona.

Prompt actual:
---
{prompt_text}
---

Sus entradas de cliente peor puntuadas, con puntajes por criterio y notas del juez:
---
{traces_desc}
---

Responde SOLO con el texto completo del prompt reescrito — sin preámbulo,
sin explicación, sin bloques de código."""
    resp = llm.chat.completions.create(
        model=DEEPSEEK_MODEL, max_tokens=4096,
        messages=[{"role": "user", "content": reflection_prompt}])
    return (resp.choices[0].message.content or "").strip()


def optimize_campaign(c, llm, client_slug: str) -> dict | None:
    campaign = c.execute(
        "SELECT id FROM docket.campaigns WHERE client_slug = %s", (client_slug,)).fetchone()
    if not campaign:
        return None
    campaign_id = campaign["id"]

    current_best = best_version(c, campaign_id)
    if not current_best:
        return None
    traces = worst_clusters(c, current_best["id"], FAILURE_TRACE_COUNT)
    if not traces:
        return None
    new_prompt_text = reflect_and_rewrite(llm, current_best["prompt_text"], traces)

    next_version_number = current_best["version_number"] + 1
    row = c.execute(
        """INSERT INTO docket.versions
               (campaign_id, version_number, prompt_text, parent_version_id, source)
           VALUES (%s, %s, %s, %s, 'gepa') RETURNING id""",
        (campaign_id, next_version_number, new_prompt_text, current_best["id"])).fetchone()
    return {"version_number": next_version_number, "id": str(row["id"])}


def run_all(campaign_slugs: list[str]) -> dict[str, dict | None]:
    if not DEEPSEEK_API_KEY:
        log.info("DEEPSEEK_API_KEY vacía: no se puede correr el optimizador (modo demo)")
        return {}
    llm = _client()
    c = store.conn()
    try:
        results = {}
        for slug in campaign_slugs:
            result = optimize_campaign(c, llm, slug)
            results[slug] = result
            if result:
                log.info("docket optimize %s: nueva versión %d (id=%s)",
                         slug, result["version_number"], result["id"])
            else:
                log.info("docket optimize %s: nada que optimizar todavía "
                         "(sin versión/cluster/score suficiente)", slug)
        c.commit()
        return results
    finally:
        c.close()
