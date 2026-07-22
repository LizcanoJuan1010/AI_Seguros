"""Lógica de captura de información (intake) para la venta de seguros.

Data-driven: todo sale del catálogo real `data/market/requisitos_seguros.json`
(KYC/Habeas Data, SARLAFT, declaración de asegurabilidad y underwriting por producto).
El agente usa estas funciones para saber QUÉ pedir, qué falta, y armar un formulario.
"""
import json
from functools import lru_cache
from typing import Any

from .config import DATA_DIR

# Mapea el tipo del catálogo de productos (español) a la clave de requisitos.
TIPO_ALIASES = {
    "vida": "vida", "salud": "salud", "auto": "auto", "hogar": "hogar",
    "viaje": "viaje", "pyme": "pyme", "accidentes": "accidentes",
}


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    return json.loads((DATA_DIR / "requisitos_seguros.json").read_text(encoding="utf-8"))


def _field_list(tipo: str) -> list[dict[str, Any]]:
    """Lista COMPLETA de campos requeridos/opcionales para un tipo de seguro,
    expandiendo grupos comunes (identificación, contacto, SARLAFT, autorizaciones)
    + los campos específicos del producto (salud/vehículo/inmueble/viaje/...)."""
    cat = _catalog()
    tipo = TIPO_ALIASES.get(tipo, tipo)
    spec = cat["por_tipo"].get(tipo)
    if not spec:
        return []
    comunes = cat["campos_comunes"]
    fields: list[dict] = []
    for grupo in spec.get("grupos", []):
        if grupo in comunes:
            for f in comunes[grupo]:
                fields.append({**f, "group": grupo})
        elif grupo in spec and isinstance(spec[grupo], list):
            # grupo específico del producto (salud, vehiculo, inmueble, viaje, pyme)
            for f in spec[grupo]:
                fields.append({**f, "group": grupo})
        elif grupo == "beneficiarios" and spec.get("grupos") and "beneficiarios" in spec["grupos"]:
            fields.append({"id": "beneficiarios", "label": "Beneficiarios (nombre, documento, parentesco, %)",
                           "tipo": "list", "required": True, "group": "beneficiarios"})
        elif grupo == "pago":
            fields.append({"id": "pago_metodo", "label": "Medio de pago", "tipo": "select",
                           "required": True, "opciones": ["PSE", "Tarjeta", "Débito", "Simulado"],
                           "group": "pago"})
    # suma asegurada / extras a nivel de tipo
    if isinstance(spec.get("suma_asegurada"), dict):
        fields.append({**spec["suma_asegurada"], "group": "cobertura"})
    for f in spec.get("extra", []) or []:
        fields.append({**f, "group": "cobertura"})
    return fields


def campos_para(tipo: str) -> list[dict[str, Any]]:
    """Todos los campos (con metadatos) del tipo de seguro."""
    return _field_list(tipo)


def _aplica(field: dict, datos: dict) -> bool:
    """Respeta condicionales (ej. pep_detalle solo si es_pep=true)."""
    cond = field.get("condicional")
    if not cond:
        return True
    val = datos.get(cond["campo"])
    if "igual" in cond:
        return val == cond["igual"]
    if "mayor_que" in cond:
        try:
            return float(val or 0) > cond["mayor_que"]
        except (ValueError, TypeError):
            return False
    return True


def faltantes(tipo: str, datos: dict) -> list[dict[str, Any]]:
    """Campos REQUERIDOS que aún no están en `datos` (respeta condicionales)."""
    out = []
    for f in _field_list(tipo):
        if not f.get("required"):
            continue
        if not _aplica(f, datos):
            continue
        v = datos.get(f["id"])
        if v is None or (isinstance(v, str) and not v.strip()):
            out.append(f)
    return out


def completitud(tipo: str, datos: dict) -> dict[str, Any]:
    """Resumen de avance del intake para un tipo."""
    req = [f for f in _field_list(tipo) if f.get("required") and _aplica(f, datos)]
    faltan = faltantes(tipo, datos)
    total = len(req) or 1
    return {
        "tipo": tipo,
        "requeridos": len(req),
        "faltantes": len(faltan),
        "completos": len(req) - len(faltan),
        "porcentaje": round(100 * (len(req) - len(faltan)) / total),
        "listo_para_emitir": len(faltan) == 0,
        "siguientes": [{"id": f["id"], "label": f["label"], "tipo": f["tipo"],
                        "opciones": f.get("opciones"), "help": f.get("help")}
                       for f in faltan[:5]],
    }


def spec_formulario(tipo: str, datos: dict | None = None) -> dict[str, Any]:
    """Especificación de un formulario para enviar al cliente (agrupado por sección).
    El frontend lo renderiza como formulario-en-chat; también sirve como 'link' de datos."""
    datos = datos or {}
    cat = _catalog()
    tipo_k = TIPO_ALIASES.get(tipo, tipo)
    nombre = cat["por_tipo"].get(tipo_k, {}).get("nombre", tipo.capitalize())
    secciones: dict[str, list] = {}
    for f in _field_list(tipo):
        if not _aplica(f, datos):
            continue
        g = f.get("group", "otros")
        secciones.setdefault(g, []).append({
            "id": f["id"], "label": f["label"], "tipo": f["tipo"],
            "required": bool(f.get("required")), "opciones": f.get("opciones"),
            "default": f.get("default"), "help": f.get("help"),
            "valor": datos.get(f["id"]),
        })
    labels = cat.get("grupos", {})
    return {
        "tipo": tipo, "titulo": f"Datos para tu {nombre}",
        "secciones": [{"grupo": g, "titulo": labels.get(g, g.capitalize()), "campos": cs}
                      for g, cs in secciones.items()],
    }


def documentos_sugeridos(tipo: str) -> list[str]:
    """Documentos que el cliente puede enviar para autocompletar (el agente los lee)."""
    docs = _catalog().get("documentos_soporte", {}).get("por_tipo", {})
    return docs.get("comun", []) + docs.get(TIPO_ALIASES.get(tipo, tipo), [])
