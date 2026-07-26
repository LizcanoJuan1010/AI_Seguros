"""Vesting de beneficios — "pagar la adquisición con inventario perecedero"
(ver Nota_estrategica_Seguros_Colsubsidio.pdf §4). Colsubsidio opera hoteles,
parques recreativos y droguerías con capacidad ociosa de costo marginal casi
nulo: en vez de un descuento al comprar, el beneficio se libera ESCALONADO
por MESES DE POLIZA VIGENTE CONTINUA — solo se entrega si la póliza
sobrevivió, así que nunca se adelanta costo de adquisición sobre prima que
nunca se cobró, y cancelar cerca de un hito cuesta algo concreto (ataca la
caída de cartera de frente, que es el problema real, no la venta inicial).

DOS escaleras según afiliación a Colsubsidio (el afiliado ya tiene tarifa de
convenio real en la red Colsubsidio — el beneficio de permanencia debe ser
claramente mayor para él; el no afiliado recibe una versión más pequeña,
limitada a viernes, sobre la misma red — nunca gratis, siempre con
descuento). Servicios reales verificados (no inventados): Clubes
recreodeportivos Colsubsidio en Bogotá (ej. BLOC), droguerías Colsubsidio,
Hoteles Colsubsidio propios (Paipa, Girardot, Llanos orientales), el parque
Piscilago (operado por Colsubsidio), y el convenio de viajes con Hoteles
Decameron vía Viajes Colsubsidio.

Aproximación necesaria: este proyecto no tiene un motor de recaudo mensual
recurrente (payments.py modela una prima única al emitir, no cobros mes a
mes) — "meses de pago continuo" se aproxima con MESES DESDE
`public.policies.start_date` mientras `status='vigente'` (si la póliza se
cancela/vence, dejan de otorgarse hitos nuevos). Documentado a propósito:
es la mejor señal disponible hoy, no un recaudo verificado mes a mes.
"""
import logging
import uuid

import psycopg
import requests

from .config import BACKEND_URL

log = logging.getLogger("seguria.benefits")

_TIMEOUT = 15

# (mes de permanencia continua, beneficio) — afiliados: acceso real/gratuito
# en la red Colsubsidio, un escalón claramente mayor que el de no afiliados.
MILESTONES_AFILIADO: list[tuple[int, str]] = [
    (3, "2 entradas GRATIS a un Club recreodeportivo Colsubsidio en Bogotá (ej. BLOC)"),
    (6, "Bono de droguería Colsubsidio"),
    (12, "Noche GRATIS en un Hotel Colsubsidio (Paipa, Girardot o Llanos orientales), "
        "o 20% de descuento en un paquete Decameron vía Viajes Colsubsidio"),
]

# No afiliados: misma red Colsubsidio, pero con DESCUENTO (no gratis) y
# restringido a los viernes — versión visiblemente más pequeña, pensada
# también como gancho para afiliarse y acceder a la escalera completa.
MILESTONES_NO_AFILIADO: list[tuple[int, str]] = [
    (3, "Entrada con descuento (solo viernes) a un Club recreodeportivo Colsubsidio en Bogotá"),
    (6, "10% de descuento en Hoteles Colsubsidio, válido los viernes"),
    (12, "Día de piscina con descuento en Piscilago, válido los viernes"),
]


def _tables(conn: psycopg.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS policy_benefits (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        policy_number TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        mes INTEGER NOT NULL,
        beneficio TEXT NOT NULL,
        codigo TEXT NOT NULL,
        entregado_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(policy_number, mes))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_policy_benefits_policy
                    ON policy_benefits (policy_number)""")


def _es_afiliado(conn: psycopg.Connection, tenant_id: str, phone: str | None) -> bool:
    """Categoría de afiliación Colsubsidio del cliente, capturada en el
    intake conversacional (`intake.afiliado_colsubsidio`, ver
    agent_core._save_intake / calls.py::_sale_context) — determina cuál de
    las dos escaleras aplica. Sin dato disponible, asume no afiliado (la
    escalera menor, nunca se sobre-promete)."""
    if not phone:
        return False
    try:
        row = conn.execute("SELECT datos FROM intake_session WHERE session_key=%s",
                           (f"{tenant_id}:{phone}",)).fetchone()
        if not row or not row.get("datos"):
            return False
        import json as _json
        datos = _json.loads(row["datos"])
        return bool(datos.get("afiliado_colsubsidio"))
    except Exception:
        conn.rollback()
        return False


def milestones_para(es_afiliado: bool) -> list[tuple[int, str]]:
    return MILESTONES_AFILIADO if es_afiliado else MILESTONES_NO_AFILIADO


def _notify(phone: str | None, policy_number: str, mes: int, beneficio: str, codigo: str) -> None:
    if not phone:
        return
    try:
        from . import whatsapp_gateway
        texto = (f"Tequendama Seguros: ¡{mes} meses con tu póliza {policy_number}! "
                f"Desbloqueaste: {beneficio}. Código: {codigo}. "
                "Muéstralo en el punto Colsubsidio correspondiente para reclamarlo.")
        whatsapp_gateway.enviar_whatsapp(phone, texto)
    except Exception:
        log.warning("no se pudo avisar el beneficio desbloqueado a %s", phone, exc_info=True)


def _notify_manager_alert(tenant_id: str, policy_number: str, beneficio: str) -> None:
    """No es un error/riesgo — es aviso operativo (alguien debe preparar/asignar
    el cupo real del beneficio). Reusa el canal de alertas existente."""
    try:
        import re
        msg = f"Beneficio de vesting desbloqueado: póliza {policy_number} — {beneficio}."
        payload = {"message": msg[:900], "severity": "info"}
        if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
                   tenant_id or "", re.I):
            payload["teamId"] = tenant_id
        requests.post(f"{BACKEND_URL}/api/v1/alerts", json=payload, timeout=5,
                     headers={"X-Tenant-Id": tenant_id})
    except Exception:
        log.debug("no se pudo crear la alerta de beneficio", exc_info=True)


def check_and_unlock(conn: psycopg.Connection) -> list[dict]:
    """Escanea pólizas VIGENTES, calcula meses de permanencia y libera (una
    sola vez por póliza+hito) los beneficios recién alcanzados, según la
    escalera de afiliación de cada cliente. Pensada para un cron diario (ver
    skill `beneficios-vesting`) — es idempotente: re-correrla el mismo día no
    vuelve a entregar nada."""
    _tables(conn)
    try:
        rows = conn.execute("""
            SELECT p.policy_number, p.start_date, c.phone, c.full_name, t.id AS team_id
            FROM public.policies p
            JOIN public.customers c ON c.id = p.customer_id
            JOIN public.teams t ON t.id = p.team_id
            WHERE p.status = 'vigente'""").fetchall()
    except Exception:
        conn.rollback()
        return []

    from datetime import date
    entregados: list[dict] = []
    for r in rows:
        meses = (date.today().year - r["start_date"].year) * 12 + \
            (date.today().month - r["start_date"].month)
        if date.today().day < r["start_date"].day:
            meses -= 1
        if meses <= 0:
            continue
        escalera = milestones_para(_es_afiliado(conn, str(r["team_id"]), r["phone"]))
        for mes, beneficio in escalera:
            if meses < mes:
                break
            ya = conn.execute(
                "SELECT 1 FROM policy_benefits WHERE policy_number=%s AND mes=%s",
                (r["policy_number"], mes)).fetchone()
            if ya:
                continue
            codigo = f"BEN-{uuid.uuid4().hex[:8].upper()}"
            conn.execute(
                """INSERT INTO policy_benefits (policy_number, tenant_id, mes, beneficio, codigo)
                   VALUES (%s,%s,%s,%s,%s)""",
                (r["policy_number"], str(r["team_id"]), mes, beneficio, codigo))
            conn.commit()
            _notify(r["phone"], r["policy_number"], mes, beneficio, codigo)
            _notify_manager_alert(str(r["team_id"]), r["policy_number"], beneficio)
            entregados.append({"policy_number": r["policy_number"], "mes": mes,
                               "beneficio": beneficio, "codigo": codigo,
                               "cliente": r["full_name"]})
    return entregados


def beneficios_de(conn: psycopg.Connection, policy_number: str) -> dict:
    """Para el tool `consultar_beneficios`: qué ya se desbloqueó y qué sigue,
    en la escalera que corresponda (afiliado/no afiliado)."""
    _tables(conn)
    try:
        row = conn.execute("""
            SELECT c.phone, p.team_id FROM public.policies p
            JOIN public.customers c ON c.id = p.customer_id
            WHERE p.policy_number = %s""", (policy_number,)).fetchone()
    except Exception:
        conn.rollback()
        row = None
    es_afiliado = _es_afiliado(conn, str(row["team_id"]), row["phone"]) if row else False
    escalera = milestones_para(es_afiliado)

    obtenidos = [dict(r) for r in conn.execute(
        """SELECT mes, beneficio, codigo, entregado_at FROM policy_benefits
           WHERE policy_number=%s ORDER BY mes""", (policy_number,)).fetchall()]
    meses_obtenidos = {r["mes"] for r in obtenidos}
    proximos = [{"mes": mes, "beneficio": beneficio} for mes, beneficio in escalera
               if mes not in meses_obtenidos]
    return {"policy_number": policy_number, "es_afiliado": es_afiliado,
           "obtenidos": obtenidos, "proximos": proximos}
