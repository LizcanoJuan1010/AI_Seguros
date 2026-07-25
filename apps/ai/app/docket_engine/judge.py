"""Base 03 (juez) — puerto de docket-motor a `docket.*`/DeepSeek.

Puntúa cada par (versión, cluster) de una campaña contra su rubric
(`rubrics/<client_slug>.json`). Salta pares ya puntuados — reruns solo
juzgan versiones/clusters nuevos. Usa el mismo cliente DeepSeek
OpenAI-SDK-compatible que `agent_core.py` (el original usa Claude; acá se
reusa el LLM ya pagado de este proyecto en vez de sumar una key nueva).
"""
import json
import logging
from pathlib import Path

from ..config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from . import store

log = logging.getLogger("seguria.docket_engine.judge")

RUBRICS_DIR = Path(__file__).parent / "rubrics"


def _client():
    from openai import OpenAI
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=60.0, max_retries=2)


def load_rubric(client_slug: str) -> dict:
    path = RUBRICS_DIR / f"{client_slug}.json"
    if not path.exists():
        raise FileNotFoundError(f"sin rubric para '{client_slug}' en {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def simulate_response(llm, prompt_text: str, customer_turn: str) -> str:
    resp = llm.chat.completions.create(
        model=DEEPSEEK_MODEL, max_tokens=1024,
        messages=[{"role": "system", "content": prompt_text},
                  {"role": "user", "content": customer_turn}])
    return resp.choices[0].message.content or ""


def score_response(llm, rubric: dict, customer_turn: str, response: str) -> list[dict]:
    criteria_desc = "\n".join(
        f"- {c['key']}: {c['description']} (escala: {c['scale']})" for c in rubric["criteria"])
    judge_prompt = f"""Estás puntuando la respuesta de un agente conversacional contra un rubric fijo.

El cliente dijo: {customer_turn}

El agente respondió: {response}

Puntúa contra cada criterio. Responde SOLO con un arreglo JSON, sin prosa,
sin bloques de código: [{{"criterion": "<key>", "score": <1-5>, "notes": "<una oración>"}}, ...]
Omite un criterio si su descripción dice que no aplica acá.

Criterios:
{criteria_desc}"""
    resp = llm.chat.completions.create(
        model=DEEPSEEK_MODEL, max_tokens=1024,
        messages=[{"role": "user", "content": judge_prompt}])
    text = (resp.choices[0].message.content or "").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


def already_scored(c, version_id: str, cluster_id: str) -> bool:
    row = c.execute(
        "SELECT id FROM docket.scores WHERE version_id = %s AND cluster_id = %s LIMIT 1",
        (version_id, cluster_id)).fetchone()
    return row is not None


def judge_campaign(c, llm, campaign: dict) -> int:
    rubric = load_rubric(campaign["client_slug"])
    versions = c.execute(
        "SELECT id, prompt_text FROM docket.versions WHERE campaign_id = %s",
        (campaign["id"],)).fetchall()
    clusters = c.execute(
        "SELECT id, representative_text FROM docket.clusters WHERE campaign_id = %s",
        (campaign["id"],)).fetchall()

    scored_pairs = 0
    for version in versions:
        for cluster in clusters:
            if already_scored(c, version["id"], cluster["id"]):
                continue
            response = simulate_response(llm, version["prompt_text"], cluster["representative_text"])
            scores = score_response(llm, rubric, cluster["representative_text"], response)
            for entry in scores:
                c.execute(
                    """INSERT INTO docket.scores (version_id, cluster_id, criterion, score, notes)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (version["id"], cluster["id"], entry["criterion"], entry["score"], entry.get("notes")))
            scored_pairs += 1
    return scored_pairs


def run_all() -> dict[str, int]:
    if not DEEPSEEK_API_KEY:
        log.info("DEEPSEEK_API_KEY vacía: no se puede correr el juez (modo demo)")
        return {}
    llm = _client()
    c = store.conn()
    try:
        campaigns = c.execute("SELECT id, client_slug FROM docket.campaigns").fetchall()
        results = {}
        for campaign in campaigns:
            try:
                count = judge_campaign(c, llm, campaign)
            except FileNotFoundError as exc:
                log.warning("docket judge %s: saltada — %s", campaign["client_slug"], exc)
                continue
            results[campaign["client_slug"]] = count
            log.info("docket judge %s: %d par(es) (versión, cluster) puntuados", campaign["client_slug"], count)
        c.commit()
        return results
    finally:
        c.close()
