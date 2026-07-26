"""Agregaciones para el panel gerencial y para la skill insights-gerente."""
from typing import Any

import psycopg

from .db import COUNTRY_NAMES

FUNNEL_ORDER = ["nuevo", "descubrimiento", "cotizado", "documento", "cerrado", "perdido"]


def summary(conn: psycopg.Connection) -> dict[str, Any]:
    totals = conn.execute(
        """SELECT (SELECT COUNT(*) FROM leads) leads,
                  (SELECT COUNT(*) FROM quotes) quotes,
                  (SELECT COUNT(*) FROM leads WHERE stage='cerrado') cerrados,
                  -- solo productos de prima mensual; los de viaje (prima_por_dia)
                  -- son por-viaje y mezclarían unidades
                  (SELECT ROUND(COALESCE(SUM(q.premium_monthly_usd),0)::numeric,2)::double precision
                     FROM quotes q JOIN products p ON p.id=q.product_id
                     WHERE q.status='aceptada' AND p.prima_por_dia=0) prima_mensual_usd"""
    ).fetchone()
    leads, cerrados = totals["leads"], totals["cerrados"]
    funnel_rows = {r["stage"]: r["n"] for r in conn.execute(
        "SELECT stage, COUNT(*) n FROM leads GROUP BY stage")}
    by_country = [
        {"country": r["country"], "pais": COUNTRY_NAMES.get(r["country"], r["country"]),
         "leads": r["leads"], "quotes": r["quotes"] or 0,
         "prima_usd": round(r["prima"] or 0, 2)}
        for r in conn.execute(
            """SELECT l.country, COUNT(DISTINCT l.id) leads,
                      COUNT(q.id) quotes, SUM(q.premium_monthly_usd) prima
               FROM leads l LEFT JOIN quotes q ON q.lead_id = l.id
               GROUP BY l.country ORDER BY leads DESC""")
    ]
    by_product = [
        {"producto": r["nombre"], "tipo": r["tipo"], "aseguradora": r["aseguradora"],
         "cotizaciones": r["n"], "prima_promedio_usd": round(r["avg_p"] or 0, 2)}
        for r in conn.execute(
            """SELECT p.nombre, p.tipo, p.aseguradora, COUNT(q.id) n,
                      AVG(q.premium_monthly_usd) avg_p
               FROM quotes q JOIN products p ON p.id = q.product_id
               GROUP BY p.id ORDER BY n DESC""")
    ]
    por_combo = by_combo(conn)
    timeseries = [
        {"fecha": r["d"], "cotizaciones": r["n"]}
        for r in conn.execute(
            """SELECT to_char(created_at,'YYYY-MM-DD') d, COUNT(*) n FROM quotes
               GROUP BY to_char(created_at,'YYYY-MM-DD') ORDER BY d""")
    ]
    # Impacto de la IA (métricas del paper McKinsey): velocidad de cotización,
    # velocidad de cierre y % de pólizas emitidas sin intervención humana.
    quoting_speed = conn.execute(
        """SELECT AVG(EXTRACT(EPOCH FROM (fq.first_q - l.created_at)))/60.0 mins
           FROM leads l JOIN (SELECT lead_id, MIN(created_at) first_q
                              FROM quotes GROUP BY lead_id) fq ON fq.lead_id = l.id
           WHERE fq.first_q >= l.created_at""").fetchone()
    close_speed = conn.execute(
        """SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at)))/86400.0 dias
           FROM leads WHERE stage='cerrado'""").fetchone()
    impacto_ia = {
        "tiempo_medio_cotizacion_min": round(quoting_speed["mins"] or 0, 1),
        "tiempo_medio_cierre_dias": round(close_speed["dias"] or 0, 1),
        "polizas_emitidas": 0,
        "pct_autoemision": 0.0,
    }
    # Pólizas del dominio Prisma (public.*); un fallo de esquema no tumba el resto.
    try:
        pol = conn.execute(
            """SELECT COUNT(*) total, COUNT(*) FILTER (WHERE agent_id IS NULL) auto
               FROM public.policies""").fetchone()
        impacto_ia["polizas_emitidas"] = pol["total"]
        impacto_ia["pct_autoemision"] = (round(100 * pol["auto"] / pol["total"], 1)
                                         if pol["total"] else 0.0)
    except Exception:
        conn.rollback()
    return {
        "kpis": {
            "leads_totales": leads,
            "cotizaciones": totals["quotes"],
            "ventas_cerradas": cerrados,
            "tasa_conversion_pct": round(100 * cerrados / leads, 1) if leads else 0.0,
            "prima_mensual_vendida_usd": totals["prima_mensual_usd"],
        },
        "impacto_ia": impacto_ia,
        "funnel": [{"etapa": s, "leads": funnel_rows.get(s, 0)} for s in FUNNEL_ORDER],
        "por_pais": by_country,
        "por_producto": by_product,
        "por_combo": por_combo,
        "cotizaciones_por_dia": timeseries,
    }


def by_combo(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Combinaciones de tipos de seguro que un mismo cliente tiene VIGENTES a
    la vez — cross-sell real (dominio Prisma, public.*), no la simulación de
    `seguria.quotes` que usa `by_product`. Solo cuenta clientes con 2+ tipos
    distintos, ordenado por frecuencia. Degrada a [] si `public.*` no está
    disponible (mismo criterio que el bloque de impacto_ia de arriba)."""
    try:
        rows = conn.execute(
            """SELECT c.id customer_id, pr.insurance_type::text tipo
               FROM public.policies p
               JOIN public.customers c ON c.id = p.customer_id
               JOIN public.quotes q ON q.id = p.quote_id
               JOIN public.products pr ON pr.id = q.product_id
               WHERE p.status = 'VIGENTE'""").fetchall()
    except Exception:
        conn.rollback()
        return []
    por_cliente: dict[str, set[str]] = {}
    for r in rows:
        por_cliente.setdefault(r["customer_id"], set()).add(r["tipo"])
    conteo: dict[tuple[str, ...], int] = {}
    for tipos in por_cliente.values():
        if len(tipos) < 2:
            continue
        combo = tuple(sorted(tipos))
        conteo[combo] = conteo.get(combo, 0) + 1
    ranking = sorted(conteo.items(), key=lambda kv: kv[1], reverse=True)
    return [{"combo": list(combo), "clientes": n} for combo, n in ranking]
