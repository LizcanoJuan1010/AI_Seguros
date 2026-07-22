"""Motor de insights proactivos (lección central de Erica: 50-60% de las
interacciones nacen de una sugerencia del asistente, no del usuario).

Reglas deterministas sobre el estado del funnel — el LLM solo redacta encima.
Consumido por: skill `seguimiento-proactivo` de Hermes (cron) y panel gerencial.
"""
from typing import Any

import psycopg

from .db import COUNTRY_NAMES


def client_nudges(conn: psycopg.Connection, phone: str | None = None) -> list[dict[str, Any]]:
    """Sugerencias de seguimiento por cliente. Sin phone: todos los accionables."""
    where, params = ("AND l.phone = %s", [phone]) if phone else ("", [])
    nudges: list[dict] = []

    # Cotizó hace 2+ días y no pidió el documento → recordatorio con su mejor opción.
    # DISTINCT ON toma la cotización más reciente por lead (equivale al MAX(created_at)
    # + columnas "bare" de SQLite, que en un MAX toman valores de esa misma fila).
    for r in conn.execute(f"""
        SELECT phone, name, country, quote_id, producto, premium_monthly_local, currency, dias
        FROM (
            SELECT DISTINCT ON (l.id)
                   l.phone, l.name, l.country, q.id quote_id, p.nombre producto,
                   q.premium_monthly_local, q.currency,
                   EXTRACT(EPOCH FROM (now() - q.created_at)) / 86400.0 dias
            FROM leads l JOIN quotes q ON q.lead_id=l.id JOIN products p ON p.id=q.product_id
            WHERE l.stage='cotizado' {where}
            ORDER BY l.id, q.created_at DESC
        ) t WHERE dias >= 2""", params):
        nudges.append({
            "phone": r["phone"], "tipo": "seguimiento_cotizacion",
            "prioridad": "alta" if r["dias"] >= 5 else "media",
            "contexto": {"producto": r["producto"], "quote_id": r["quote_id"],
                         "prima": f"{r['premium_monthly_local']:,.0f} {r['currency']}",
                         "dias_sin_respuesta": int(r["dias"])},
            "sugerencia": f"Recordarle a {r['name'] or 'el cliente'} su cotización de "
                          f"{r['producto']} ({r['premium_monthly_local']:,.0f} {r['currency']}/mes) "
                          f"y ofrecer resolver dudas o ajustar la suma.",
        })

    # Recibió el documento y no cerró en 3+ días → oferta de llamada con asesor
    for r in conn.execute(f"""
        SELECT l.phone, l.name, EXTRACT(EPOCH FROM (now() - l.updated_at)) / 86400.0 dias
        FROM leads l WHERE l.stage='documento' {where}""", params):
        if r["dias"] >= 3:
            nudges.append({
                "phone": r["phone"], "tipo": "cierre_pendiente", "prioridad": "alta",
                "contexto": {"dias_desde_documento": int(r["dias"])},
                "sugerencia": f"Ofrecer a {r['name'] or 'el cliente'} agendar la llamada con el "
                              "asesor licenciado o resolver la duda que lo frena.",
            })

    # En descubrimiento sin cotizar hace 1+ día → retomar con una pregunta simple
    for r in conn.execute(f"""
        SELECT l.phone, l.name, l.country,
               EXTRACT(EPOCH FROM (now() - l.updated_at)) / 86400.0 dias
        FROM leads l WHERE l.stage IN ('nuevo','descubrimiento') {where}""", params):
        if r["dias"] >= 1:
            nudges.append({
                "phone": r["phone"], "tipo": "retomar_descubrimiento", "prioridad": "baja",
                "contexto": {"pais": COUNTRY_NAMES.get(r["country"], r["country"]),
                             "dias_inactivo": int(r["dias"])},
                "sugerencia": f"Retomar con {r['name'] or 'el cliente'} con UNA pregunta concreta "
                              "sobre su necesidad (no un genérico '¿sigues ahí?').",
            })
    prio = {"alta": 0, "media": 1, "baja": 2}
    nudges.sort(key=lambda n: prio[n["prioridad"]])
    return nudges


def manager_alerts(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Alertas de negocio para el gerente."""
    alerts: list[dict] = []
    k = conn.execute("""
        SELECT (SELECT COUNT(*) FROM leads) leads,
               (SELECT COUNT(*) FROM leads WHERE stage='cerrado') cerrados,
               (SELECT COUNT(*) FROM leads WHERE stage='cotizado'
                  AND updated_at <= now() - interval '3 days') estancados,
               (SELECT COUNT(*) FROM quotes
                  WHERE created_at >= now() - interval '7 days') cotiz_7d""").fetchone()
    conv = round(100 * k["cerrados"] / k["leads"], 1) if k["leads"] else 0
    if conv < 20 and k["leads"] >= 10:
        alerts.append({"tipo": "conversion_baja", "prioridad": "alta",
                       "detalle": f"Conversión lead→venta en {conv}% (objetivo ≥20%).",
                       "accion": "Revisar objeciones registradas en los leads perdidos y reforzar el cierre."})
    if k["estancados"]:
        alerts.append({"tipo": "leads_estancados", "prioridad": "media",
                       "detalle": f"{k['estancados']} leads llevan 3+ días en 'cotizado' sin avanzar.",
                       "accion": "Lanzar la campaña de seguimiento proactivo (ver /api/proactive)."})
    if k["cotiz_7d"] == 0:
        alerts.append({"tipo": "sin_actividad", "prioridad": "alta",
                       "detalle": "Cero cotizaciones en los últimos 7 días.",
                       "accion": "Verificar el canal de WhatsApp y la campaña de adquisición."})
    top = conn.execute("""
        SELECT p.nombre, COUNT(*) n FROM quotes q JOIN products p ON p.id=q.product_id
        WHERE q.created_at >= now() - interval '7 days'
        GROUP BY p.id ORDER BY n DESC LIMIT 1""").fetchone()
    if top:
        alerts.append({"tipo": "tendencia", "prioridad": "info",
                       "detalle": f"Producto más cotizado (7 días): {top['nombre']} ({top['n']} cotizaciones).",
                       "accion": "Considerar destacarlo en la bienvenida del asistente."})
    return alerts
