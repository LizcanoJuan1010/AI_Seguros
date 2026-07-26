"""Informes periódicos por correo (patrón portado de Paloma: daily brief + outbox).

Dos audiencias:
  - CLIENTE: opt-in conversacional ("¿quieres un informe mensual de tu
    seguro?") → resumen de sus cotizaciones/pólizas y su etapa en el funnel.
  - GERENTE: KPIs del negocio (leads, cotizaciones, cierres, prima vendida).

Una tabla `report_subscriptions` guarda la preferencia (email + frecuencia) y
un planificador asíncrono (loop cada 60 s, como el outbox de Paloma) envía los
informes vencidos y reprograma el siguiente. El envío usa email_service
(SMTP → Resend) y si no hay proveedor configurado marca "skipped" sin romper.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg

from .db import get_conn
from .insights import summary as insights_summary

log = logging.getLogger("seguria.reports")

FRECUENCIAS: dict[str, timedelta] = {
    "demo": timedelta(minutes=2),      # para probar el flujo en vivo
    "diaria": timedelta(days=1),
    "semanal": timedelta(days=7),
    "mensual": timedelta(days=30),
}

_SCHEDULER_TICK_S = 60

DDL = """CREATE TABLE IF NOT EXISTS report_subscriptions (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'cliente',        -- cliente|gerente
    frecuencia TEXT NOT NULL DEFAULT 'mensual',  -- demo|diaria|semanal|mensual
    phone TEXT,                                  -- referencia al lead (clientes)
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    last_sent_at TIMESTAMPTZ,
    next_send_at TIMESTAMPTZ NOT NULL,
    UNIQUE (email, tipo)
)"""


def _ensure_table(conn: psycopg.Connection) -> None:
    conn.execute(DDL)


def subscribe(email: str, *, tipo: str = "cliente", frecuencia: str = "mensual",
              phone: str | None = None) -> dict[str, Any]:
    """Alta (o actualización) de la suscripción. Devuelve el registro."""
    email = (email or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return {"error": "email inválido"}
    if tipo not in ("cliente", "gerente"):
        return {"error": f"tipo inválido: {tipo}"}
    if frecuencia not in FRECUENCIAS:
        return {"error": f"frecuencia inválida: {frecuencia}",
                "validas": list(FRECUENCIAS)}
    nxt = datetime.now(timezone.utc) + FRECUENCIAS[frecuencia]
    conn = get_conn()
    try:
        _ensure_table(conn)
        row = conn.execute(
            """INSERT INTO report_subscriptions (email, tipo, frecuencia, phone, next_send_at)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (email, tipo) DO UPDATE
                 SET frecuencia=EXCLUDED.frecuencia, phone=COALESCE(EXCLUDED.phone,
                     report_subscriptions.phone), activo=TRUE,
                     next_send_at=EXCLUDED.next_send_at
               RETURNING id, email, tipo, frecuencia, next_send_at""",
            (email, tipo, frecuencia, phone, nxt)).fetchone()
        conn.commit()
        return {"ok": True, **{k: (v.isoformat() if isinstance(v, datetime) else v)
                               for k, v in dict(row).items()}}
    finally:
        conn.close()


def list_subscriptions() -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        _ensure_table(conn)
        rows = conn.execute(
            """SELECT id, email, tipo, frecuencia, phone, activo,
                      last_sent_at, next_send_at
               FROM report_subscriptions WHERE activo ORDER BY id DESC LIMIT 100"""
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for k in ("last_sent_at", "next_send_at"):
                if isinstance(d.get(k), datetime):
                    d[k] = d[k].isoformat()
            out.append(d)
        return out
    finally:
        conn.close()


def unsubscribe(sub_id: int) -> bool:
    conn = get_conn()
    try:
        _ensure_table(conn)
        cur = conn.execute(
            "UPDATE report_subscriptions SET activo=FALSE WHERE id=%s", (sub_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Contenido de los informes (HTML sencillo con la paleta Mist/Forest)
# --------------------------------------------------------------------------- #

_STYLE = ("font-family:Arial,Helvetica,sans-serif;color:#141e17;"
          "background:#f1fdf0;padding:24px")
_CARD = ("background:#ffffff;border:1px solid #c1c9bd;border-radius:12px;"
         "padding:20px;margin:12px 0")
_H = "color:#083911;margin:0 0 8px"
_AMBER = "color:#795900;font-weight:bold"


def _wrap(title: str, inner: str) -> str:
    return (f'<div style="{_STYLE}"><h2 style="{_H}">{title}</h2>{inner}'
            f'<p style="color:#72796f;font-size:12px;margin-top:20px">'
            f"Tequendama Seguros · IA de protección · Puedes cancelar estos "
            f"informes respondiendo a este correo o desde tu asistente.</p></div>")


def build_client_report_html(conn: psycopg.Connection, phone: str | None) -> str:
    lead = None
    if phone:
        lead = conn.execute(
            "SELECT * FROM leads WHERE phone=%s", (phone,)).fetchone()
    if not lead:
        inner = (f'<div style="{_CARD}"><p>Aún no tienes cotizaciones o pólizas '
                 f"activas con nosotros. Cuando quieras, tu asesora IA te cotiza "
                 f"en minutos: vida, auto, hogar, mascotas y más.</p></div>")
        return _wrap("Tu informe de seguros", inner)

    quotes = conn.execute(
        """SELECT q.*, p.nombre producto, p.aseguradora
           FROM quotes q JOIN products p ON p.id=q.product_id
           WHERE q.lead_id=%s ORDER BY q.created_at DESC LIMIT 5""",
        (lead["id"],)).fetchall()
    rows = "".join(
        f"<tr><td style='padding:6px 10px'>{q['producto']}</td>"
        f"<td style='padding:6px 10px'>{q['aseguradora']}</td>"
        f"<td style='padding:6px 10px'><span style='{_AMBER}'>"
        f"{q['premium_monthly_local']:,.0f} {q['currency']}/mes</span></td>"
        f"<td style='padding:6px 10px'>{q['status']}</td></tr>"
        for q in quotes) or ("<tr><td style='padding:6px 10px' colspan='4'>"
                             "Sin cotizaciones recientes.</td></tr>")
    inner = (
        f'<div style="{_CARD}"><p style="margin:0">Hola '
        f"<b>{lead['name'] or 'cliente'}</b>, este es el estado de tu protección "
        f"(etapa: <b>{lead['stage']}</b>):</p></div>"
        f'<div style="{_CARD}"><table style="border-collapse:collapse;width:100%">'
        f"<tr><th align='left' style='padding:6px 10px'>Producto</th>"
        f"<th align='left' style='padding:6px 10px'>Aseguradora</th>"
        f"<th align='left' style='padding:6px 10px'>Prima</th>"
        f"<th align='left' style='padding:6px 10px'>Estado</th></tr>{rows}</table></div>"
        f'<div style="{_CARD}"><p style="margin:0">💡 ¿Cambió algo en tu vida '
        f"(carro nuevo, mudanza, familia)? Escríbele a tu asesora IA y ajustamos "
        f"tu cobertura en minutos.</p></div>")
    return _wrap("Tu informe de seguros", inner)


def build_manager_report_html(conn: psycopg.Connection) -> str:
    s = insights_summary(conn)
    k = s["kpis"]
    kpis = "".join(
        f'<td style="padding:10px 16px;text-align:center"><div style="{_AMBER};'
        f'font-size:22px">{v}</div><div style="color:#72796f;font-size:12px">{lbl}'
        f"</div></td>"
        for lbl, v in (
            ("Leads", k["leads_totales"]), ("Cotizaciones", k["cotizaciones"]),
            ("Cierres", k["ventas_cerradas"]),
            ("Conversión", f"{k['tasa_conversion_pct']}%"),
            ("Prima vendida (USD/mes)", f"${k['prima_mensual_vendida_usd']:,.0f}"),
        ))
    funnel = "".join(
        f"<tr><td style='padding:4px 10px'>{f['etapa']}</td>"
        f"<td style='padding:4px 10px;text-align:right'>{f['leads']}</td></tr>"
        for f in s["funnel"])
    inner = (
        f'<div style="{_CARD}"><table style="width:100%"><tr>{kpis}</tr></table></div>'
        f'<div style="{_CARD}"><h3 style="{_H}">Funnel</h3>'
        f'<table style="border-collapse:collapse">{funnel}</table></div>')
    return _wrap("Reporte gerencial · Tequendama Seguros", inner)


# --------------------------------------------------------------------------- #
# Envío + planificador
# --------------------------------------------------------------------------- #

async def send_subscription_now(sub: dict[str, Any]) -> dict[str, Any]:
    """Construye y envía el informe de una suscripción; reprograma el siguiente."""
    from .email_service import send_email
    conn = get_conn()
    try:
        if sub["tipo"] == "gerente":
            html = build_manager_report_html(conn)
            subject = "Reporte gerencial de Tequendama Seguros"
        else:
            html = build_client_report_html(conn, sub.get("phone"))
            subject = "Tu informe de seguros · Tequendama"
    finally:
        conn.close()

    result = await send_email(sub["email"], subject, html)

    now = datetime.now(timezone.utc)
    if result.get("status") == "sent":
        delta = FRECUENCIAS.get(sub["frecuencia"], FRECUENCIAS["mensual"])
    else:
        # NO marcar como enviado lo que no salió: un informe mensual que caía
        # en la hora del circuito abierto de Resend quedaba "enviado" y no se
        # reintentaba en 30 días. Reintento en 15 min (el scheduler lo
        # recoge); last_sent_at solo avanza con envíos reales.
        log.warning("informe a %s no salió (%s: %s); reintento en 15 min",
                    sub["email"], result.get("status"), result.get("reason"))
        delta = timedelta(minutes=15)
    conn = get_conn()
    try:
        _ensure_table(conn)
        if result.get("status") == "sent":
            conn.execute(
                """UPDATE report_subscriptions
                   SET last_sent_at=%s, next_send_at=%s WHERE id=%s""",
                (now, now + delta, sub["id"]))
        else:
            conn.execute(
                """UPDATE report_subscriptions
                   SET next_send_at=%s WHERE id=%s""",
                (now + delta, sub["id"]))
        conn.commit()
    finally:
        conn.close()
    return result


async def scheduler_loop() -> None:
    """Cada 60 s envía los informes vencidos (patrón outbox de Paloma)."""
    log.info("planificador de informes activo (tick=%ss)", _SCHEDULER_TICK_S)
    while True:
        try:
            conn = get_conn()
            try:
                _ensure_table(conn)
                due = conn.execute(
                    """SELECT id, email, tipo, frecuencia, phone
                       FROM report_subscriptions
                       WHERE activo AND next_send_at <= now() LIMIT 20""").fetchall()
                conn.commit()
            finally:
                conn.close()
            for sub in due:
                result = await send_subscription_now(dict(sub))
                log.info("informe %s → %s: %s", sub["tipo"], sub["email"],
                         result.get("status"))
        except Exception:
            log.exception("tick del planificador de informes falló")
        await asyncio.sleep(_SCHEDULER_TICK_S)
