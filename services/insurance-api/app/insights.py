"""Agregaciones para el panel gerencial y para la skill insights-gerente."""
import sqlite3
from typing import Any

from .db import COUNTRY_NAMES

FUNNEL_ORDER = ["nuevo", "descubrimiento", "cotizado", "documento", "cerrado", "perdido"]


def summary(conn: sqlite3.Connection) -> dict[str, Any]:
    totals = conn.execute(
        """SELECT (SELECT COUNT(*) FROM leads) leads,
                  (SELECT COUNT(*) FROM quotes) quotes,
                  (SELECT COUNT(*) FROM leads WHERE stage='cerrado') cerrados,
                  -- solo productos de prima mensual; los de viaje (prima_por_dia)
                  -- son por-viaje y mezclarían unidades
                  (SELECT ROUND(COALESCE(SUM(q.premium_monthly_usd),0),2)
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
    timeseries = [
        {"fecha": r["d"], "cotizaciones": r["n"]}
        for r in conn.execute(
            """SELECT date(created_at) d, COUNT(*) n FROM quotes
               GROUP BY date(created_at) ORDER BY d""")
    ]
    return {
        "kpis": {
            "leads_totales": leads,
            "cotizaciones": totals["quotes"],
            "ventas_cerradas": cerrados,
            "tasa_conversion_pct": round(100 * cerrados / leads, 1) if leads else 0.0,
            "prima_mensual_vendida_usd": totals["prima_mensual_usd"],
        },
        "funnel": [{"etapa": s, "leads": funnel_rows.get(s, 0)} for s in FUNNEL_ORDER],
        "por_pais": by_country,
        "por_producto": by_product,
        "cotizaciones_por_dia": timeseries,
    }
