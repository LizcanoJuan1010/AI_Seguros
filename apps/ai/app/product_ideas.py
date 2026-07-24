"""Muro de ideas de producto: demanda no cubierta detectada en conversaciones.

Escanea los mensajes de clientes (tabla `conversations`) buscando menciones de
tipos de seguro que el catálogo NO ofrece hoy (mascotas, moto, dispositivos,
desempleo...). Para cada tema con demanda arma una "idea de producto" con:
menciones, frases de ejemplo reales, y una viabilidad explicada que cruza la
demanda con la capacidad de pago de los solicitantes (customer_profile).

Es heurística determinista (sin LLM): explicable, instantánea y sin costo —
el mismo criterio del motor de scoring de leads. Cache en memoria por 5 min.
"""
import json
import re
import time
import unicodedata

from .db import get_conn

# Temas de demanda: claves de detección -> metadatos del posible producto.
# `tipo_catalogo` permite marcar el tema como cubierto si el catálogo ya
# vende ese tipo (la idea entonces no aparece, o aparece como extensión).
TOPICS: list[dict] = [
    {
        "tema": "mascotas",
        "titulo": "Seguro para mascotas",
        "keywords": ("mascota", "perro", "gato", "veterinari"),
        "tipo_catalogo": "mascotas",
        "nota": "Cobertura veterinaria y responsabilidad civil por tenencia.",
    },
    {
        "tema": "moto",
        "titulo": "Seguro para motos",
        "keywords": ("moto", "motocicleta", "scooter"),
        "tipo_catalogo": "moto",
        "nota": "SOAT complementario, todo riesgo parcial para motos de trabajo.",
    },
    {
        "tema": "dispositivos",
        "titulo": "Seguro de celular y dispositivos",
        "keywords": ("celular", "telefono", "portatil", "laptop", "tablet", "computador"),
        "tipo_catalogo": "dispositivos",
        "nota": "Robo y daño accidental de dispositivos personales.",
    },
    {
        "tema": "desempleo",
        "titulo": "Seguro de desempleo / protección de ingresos",
        "keywords": ("desempleo", "quedo sin trabajo", "pierdo el trabajo", "sin empleo"),
        "tipo_catalogo": "desempleo",
        "nota": "Cuotas cubiertas por N meses ante pérdida involuntaria del empleo.",
    },
    {
        "tema": "bicicleta",
        "titulo": "Seguro para bicicletas",
        "keywords": ("bicicleta", "bici electrica", "patineta"),
        "tipo_catalogo": "bicicleta",
        "nota": "Robo y accidentes para movilidad ligera urbana.",
    },
    {
        "tema": "agro",
        "titulo": "Seguro agropecuario",
        "keywords": ("cosecha", "cultivo", "ganado", "finca"),
        "tipo_catalogo": "agro",
        "nota": "Clima y pérdida de cosecha para pequeños productores.",
    },
    {
        "tema": "arriendo",
        "titulo": "Seguro de arrendamiento para inquilinos",
        "keywords": ("deposito de arriendo", "codeudor", "fiador"),
        "tipo_catalogo": "hogar",
        "nota": "Reemplaza codeudor; el catálogo cubre al arrendador, no al inquilino.",
    },
]

_CACHE_TTL_SEC = 300
_cache: dict[str, tuple[float, dict]] = {}


def _norm(text: str) -> str:
    """minúsculas y sin tildes para matching robusto."""
    t = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _viabilidad(menciones: int, telefonos: set[str], capacidades: list[float]) -> tuple[str, str]:
    """(nivel, razón). Demanda repetida + capacidad de pago = viable."""
    solicitantes = len(telefonos) or 1
    cap_media = sum(capacidades) / len(capacidades) if capacidades else None
    razones = [f"{menciones} mención(es) de {solicitantes} cliente(s) distintos"]
    if cap_media is not None:
        razones.append(
            f"capacidad de pago media de los solicitantes: ${cap_media:,.0f} COP/mes")
    if menciones >= 3 and (cap_media or 0) >= 300_000:
        nivel = "alta"
        razones.append("demanda recurrente con capacidad de pago demostrada")
    elif menciones >= 2:
        nivel = "media"
        razones.append("demanda repetida; validar con una campaña piloto")
    else:
        nivel = "baja"
        razones.append("mención aislada; monitorear si se repite")
    return nivel, " · ".join(razones)


def product_ideas(tenant_id: str) -> dict:
    """Ideas de producto no cubiertas para el muro del gerente (con cache)."""
    now = time.time()
    cached = _cache.get(tenant_id)
    if cached and now - cached[0] < _CACHE_TTL_SEC:
        return cached[1]

    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT phone, message, created_at FROM conversations
               WHERE role = 'cliente' ORDER BY created_at DESC LIMIT 1000"""
        ).fetchall()
        tipos_catalogo = {
            r["tipo"] for r in conn.execute("SELECT DISTINCT tipo FROM products").fetchall()
        }
        # Capacidad de pago por teléfono (para la viabilidad).
        perfiles = {
            r["phone"]: r["perfil"]
            for r in conn.execute(
                "SELECT phone, perfil FROM customer_profile").fetchall()
        }
    finally:
        conn.close()

    ideas = []
    for topic in TOPICS:
        if topic["tipo_catalogo"] in tipos_catalogo and topic["tema"] != "arriendo":
            continue  # ya existe producto de ese tipo: no es idea nueva
        menciones = 0
        telefonos: set[str] = set()
        ejemplos: list[str] = []
        capacidades: list[float] = []
        for row in rows:
            msg = _norm(row["message"] or "")
            if any(_norm(k) in msg for k in topic["keywords"]):
                menciones += 1
                phone = row["phone"] or ""
                if phone and phone not in telefonos:
                    perfil = perfiles.get(phone)
                    if isinstance(perfil, str):
                        try:
                            perfil = json.loads(perfil)
                        except ValueError:
                            perfil = None
                    cap = (perfil or {}).get("capacidad_pago_mensual_cop")
                    if isinstance(cap, (int, float)):
                        capacidades.append(float(cap))
                telefonos.add(phone)
                if len(ejemplos) < 3:
                    clean = re.sub(r"\s+", " ", row["message"]).strip()
                    ejemplos.append(clean[:140])
        if menciones == 0:
            continue
        nivel, razon = _viabilidad(menciones, telefonos, capacidades)
        ideas.append({
            "tema": topic["tema"],
            "titulo": topic["titulo"],
            "descripcion": topic["nota"],
            "menciones": menciones,
            "solicitantes": len({t for t in telefonos if t}),
            "ejemplos": ejemplos,
            "viabilidad": nivel,
            "razon_viabilidad": razon,
        })

    orden = {"alta": 0, "media": 1, "baja": 2}
    ideas.sort(key=lambda i: (orden[i["viabilidad"]], -i["menciones"]))
    result = {
        "ideas": ideas,
        "mensajes_analizados": len(rows),
        "generado_por": "heuristica",
    }
    _cache[tenant_id] = (now, result)
    return result
