"""Base 02 (clustering) — puerto de docket-motor a `docket.*`/psycopg 3.

Agrupa los turnos de cliente (`docket.calls.raw_meta->'turns'`) de cada
campaña con embeddings + HDBSCAN, para que el juez (`judge.py`) puntúe un
representante por cluster en vez de cada turno individual. Full recompute por
campaña en cada corrida (no upsert incremental) — reruns no duplican porque
borra los clusters/call_turns de esa campaña antes de reinsertar.

Requiere `sentence-transformers`+`hdbscan` (deps pesadas, agregadas solo para
esto — ver requirements.txt). Se invoca desde el endpoint de recompute
(`POST /api/docket/recompute`), no como cron.
"""
import logging

import numpy as np

from . import store

log = logging.getLogger("seguria.docket_engine.cluster")

_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def _to_vector_literal(embedding) -> str:
    return "[" + ",".join(str(float(x)) for x in embedding) + "]"


def fetch_customer_turns(c, campaign_id: str) -> list[dict]:
    calls = c.execute(
        "SELECT id, raw_meta FROM docket.calls WHERE campaign_id = %s", (campaign_id,)
    ).fetchall()
    turns = []
    for call in calls:
        for turn in (call["raw_meta"] or {}).get("turns", []):
            if turn.get("role") != "customer" or not (turn.get("text") or "").strip():
                continue
            turns.append({
                "call_id": call["id"], "text": turn["text"],
                "start": turn.get("start"), "end": turn.get("end"),
                "pitch_mean_hz": turn.get("pitch_mean_hz"),
                "pitch_std_hz": turn.get("pitch_std_hz"),
                "energy_rms": turn.get("energy_rms"),
                "speaking_rate_wps": turn.get("speaking_rate_wps"),
            })
    return turns


def cluster_campaign(c, campaign_id: str) -> int:
    import hdbscan

    turns = fetch_customer_turns(c, campaign_id)
    # HDBSCAN (min_cluster_size=5 por defecto) revienta con un ValueError de
    # sklearn ("k must be less than or equal to the number of training
    # points") si hay menos puntos que eso — normal al principio, con pocas
    # conversaciones reales todavía. Nada que clusterizar con tan pocos datos.
    if len(turns) < 5:
        log.info("campaña %s: %d turno(s) de cliente, insuficientes para clusterizar (mínimo 5)",
                 campaign_id, len(turns))
        return 0

    # ON DELETE no está en cascada — call_turns primero, luego clusters.
    c.execute(
        "DELETE FROM docket.call_turns WHERE cluster_id IN "
        "(SELECT id FROM docket.clusters WHERE campaign_id = %s)", (campaign_id,))
    c.execute("DELETE FROM docket.clusters WHERE campaign_id = %s", (campaign_id,))

    embeddings = _get_embedder().encode([t["text"] for t in turns])
    labels = hdbscan.HDBSCAN(metric="euclidean").fit_predict(embeddings)

    cluster_count = 0
    for label in sorted(set(labels)):
        if label == -1:
            continue  # ruido — nada útil que el juez pueda puntuar

        member_idx = [i for i, l in enumerate(labels) if l == label]
        member_embeddings = embeddings[member_idx]
        centroid = member_embeddings.mean(axis=0)
        distances = np.linalg.norm(member_embeddings - centroid, axis=1)
        representative = turns[member_idx[int(np.argmin(distances))]]

        pitch_stds = [turns[i]["pitch_std_hz"] for i in member_idx if turns[i]["pitch_std_hz"] is not None]
        energies = [turns[i]["energy_rms"] for i in member_idx if turns[i]["energy_rms"] is not None]
        avg_pitch_std_hz = float(np.mean(pitch_stds)) if pitch_stds else None
        avg_energy_rms = float(np.mean(energies)) if energies else None

        row = c.execute(
            """INSERT INTO docket.clusters
                   (campaign_id, representative_text, size, avg_pitch_std_hz, avg_energy_rms)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (campaign_id, representative["text"], len(member_idx), avg_pitch_std_hz, avg_energy_rms),
        ).fetchone()
        cluster_id = row["id"]
        cluster_count += 1

        for i in member_idx:
            c.execute(
                """INSERT INTO docket.call_turns
                       (call_id, cluster_id, role, turn_text, start_seconds, end_seconds,
                        pitch_mean_hz, pitch_std_hz, energy_rms, speaking_rate_wps, embedding)
                   VALUES (%s, %s, 'customer', %s, %s, %s, %s, %s, %s, %s, %s::vector)""",
                (turns[i]["call_id"], cluster_id, turns[i]["text"], turns[i]["start"], turns[i]["end"],
                 turns[i]["pitch_mean_hz"], turns[i]["pitch_std_hz"], turns[i]["energy_rms"],
                 turns[i]["speaking_rate_wps"], _to_vector_literal(embeddings[i])),
            )

    return cluster_count


def run_all() -> dict[str, int]:
    """Clusteriza todas las campañas sembradas. Devuelve {client_slug: n_clusters}."""
    c = store.conn()
    try:
        campaigns = c.execute("SELECT id, client_slug FROM docket.campaigns").fetchall()
        results = {}
        for campaign in campaigns:
            count = cluster_campaign(c, campaign["id"])
            results[campaign["client_slug"]] = count
            log.info("docket cluster %s: %d cluster(s)", campaign["client_slug"], count)
        c.commit()
        return results
    finally:
        c.close()
