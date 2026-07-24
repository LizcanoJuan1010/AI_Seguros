"""Motor de insights proactivos (lección central de Erica: 50-60% de las
interacciones nacen de una sugerencia del asistente, no del usuario).

Reglas deterministas sobre el estado del funnel — el LLM solo redacta encima.
Consumido por: skill `seguimiento-proactivo` de Hermes (cron) y panel gerencial.

Incluye nudges sobre PÓLIZAS EMITIDAS (renovación próxima y cross-sell), leyendo
las tablas del dominio Prisma en `public.*` (mismo Postgres, otro esquema).
"""
from datetime import date
from typing import Any

import psycopg

from .db import COUNTRY_NAMES

# Cross-sell: si tiene el tipo de la izquierda y no el de la derecha, sugerirlo.
# (InsuranceType del dominio: vida | auto | salud, en minúscula en la BD.)
_CROSS_SELL = [("auto", "vida"), ("vida", "salud"), ("salud", "vida")]

_PRIO = {"alta": 0, "media": 1, "baja": 2}


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
    nudges.sort(key=lambda n: _PRIO[n["prioridad"]])
    return nudges


def policy_nudges(conn: psycopg.Connection, phone: str | None = None) -> list[dict[str, Any]]:
    """Nudges sobre pólizas emitidas: renovación próxima y cross-sell.

    Lee `public.policies/customers/quotes/products` (dominio Prisma). Si esas
    tablas no existen (tests con esquema aislado), devuelve [] sin romper la
    conexión (rollback para no dejar la transacción en estado fallido)."""
    nudges: list[dict] = []
    where, params = ("AND c.phone = %s", [phone]) if phone else ("", [])

    # Renovación: póliza vigente que vence en ≤30 días → renovar antes del corte.
    try:
        for r in conn.execute(f"""
            SELECT p.policy_number, p.end_date, p.monthly_premium_cop::float prima,
                   pr.insurance_type::text tipo, c.full_name, c.phone
            FROM public.policies p
            JOIN public.customers c ON c.id = p.customer_id
            JOIN public.quotes q ON q.id = p.quote_id
            JOIN public.products pr ON pr.id = q.product_id
            WHERE p.status = 'vigente'
              AND p.end_date <= CURRENT_DATE + INTERVAL '30 days' {where}
            ORDER BY p.end_date""", params):
            dias = (r["end_date"] - date.today()).days
            nudges.append({
                "phone": r["phone"], "tipo": "renovacion_proxima",
                "prioridad": "alta" if dias <= 7 else "media",
                "contexto": {"poliza": r["policy_number"], "tipo_seguro": r["tipo"],
                             "vence_en_dias": max(dias, 0),
                             "prima_actual_cop": r["prima"]},
                "sugerencia": f"La póliza {r['policy_number']} de "
                              f"{r['full_name'] or 'el cliente'} vence en {max(dias, 0)} días: "
                              "ofrecer la renovación pre-cotizada (proponer_renovacion) "
                              "antes de que quede sin cobertura.",
            })
    except Exception:
        conn.rollback()
        return nudges

    # Cross-sell: tiene un tipo vigente y le falta el complementario recomendado.
    try:
        for r in conn.execute(f"""
            SELECT c.full_name, c.phone,
                   array_agg(DISTINCT pr.insurance_type::text) tipos
            FROM public.policies p
            JOIN public.customers c ON c.id = p.customer_id
            JOIN public.quotes q ON q.id = p.quote_id
            JOIN public.products pr ON pr.id = q.product_id
            WHERE p.status = 'vigente' {where}
            GROUP BY c.id, c.full_name, c.phone""", params):
            tipos = set(r["tipos"] or [])
            sugerido = next((dst for src, dst in _CROSS_SELL
                             if src in tipos and dst not in tipos), None)
            if sugerido:
                nudges.append({
                    "phone": r["phone"], "tipo": "cross_sell", "prioridad": "baja",
                    "contexto": {"tiene": sorted(tipos), "sugerido": sugerido},
                    "sugerencia": f"{r['full_name'] or 'El cliente'} ya tiene "
                                  f"{', '.join(sorted(tipos))}: ofrecerle un seguro de "
                                  f"{sugerido} como complemento natural de su protección.",
                })
    except Exception:
        conn.rollback()
    nudges.sort(key=lambda n: _PRIO[n["prioridad"]])
    return nudges


def all_nudges(conn: psycopg.Connection, phone: str | None = None) -> list[dict[str, Any]]:
    """Funnel de venta + pólizas emitidas, ordenados por prioridad."""
    merged = client_nudges(conn, phone) + policy_nudges(conn, phone)
    merged.sort(key=lambda n: _PRIO[n["prioridad"]])
    return merged


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
    # Renovaciones próximas (dominio public.*): va al final para que un fallo de
    # esquema no invalide la transacción de las alertas anteriores.
    try:
        n = conn.execute(
            """SELECT COUNT(*) n FROM public.policies
               WHERE status='vigente'
                 AND end_date <= CURRENT_DATE + INTERVAL '30 days'""").fetchone()["n"]
        if n:
            alerts.append({"tipo": "renovaciones_proximas", "prioridad": "alta",
                           "detalle": f"{n} póliza(s) vigente(s) vencen en los próximos 30 días.",
                           "accion": "Lanzar la campaña de renovación proactiva "
                                     "(nudges renovacion_proxima en /api/proactive)."})
    except Exception:
        conn.rollback()
    return alerts
