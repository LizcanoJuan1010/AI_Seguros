"""Hiper-perfilamiento determinista del cliente para la venta de seguros.

A partir de los datos recolectados durante la conversación de WhatsApp
(catálogo real en data/market/requisitos_seguros.json) infiere un perfil
rico que permite personalizar la venta: etapa de vida, segmento de riesgo,
capacidad de pago, necesidades de aseguramiento, propensión de compra y
banderas de underwriting/compliance.

Diseño:
- Función PURA y DETERMINISTA: mismas entradas -> misma salida. La única
  dependencia del "hoy" (cálculo de edad) puede fijarse con
  ``contexto["fecha_referencia"]`` (AAAA-MM-DD) para pruebas reproducibles.
- ROBUSTA a datos faltantes: nunca lanza excepción por campos ausentes;
  todo se lee con ``.get`` y valores por defecto.
- SOLO stdlib (``datetime``). Sin dependencias externas.

Punto de entrada: ``build_profile(datos, contexto)``.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Tokens que, como PRIMERA palabra de una respuesta de texto libre, indican
# AUSENCIA de la condición ("no fumo", "ninguna", "nunca", "sin novedad"...).
# El intake guarda varios campos de salud como texto (ver requisitos_seguros:
# fumador, enfermedades, preexistencias, deportes_riesgo), no como booleanos.
# ---------------------------------------------------------------------------
_NEG_FIRST_WORDS = {
    "no", "ninguna", "ninguno", "ningun", "ningún", "nunca", "nada",
    "sin", "none", "n/a", "na", "-", "negativo", "0",
}
# Valores completos que también significan ausencia.
_NEG_FULL = {"no", "false", "0", "-", "n/a", "na", ""}

# Palabras afirmativas para campos que llegan como texto/booleano suelto.
_AFF_FULL = {"si", "sí", "yes", "true", "1", "afirmativo", "verdadero"}

# Ocupaciones/actividades intrínsecamente riesgosas (underwriting Fasecolda).
_OCUP_RIESGO_KW = (
    "altura", "minero", "mineria", "minería", "explosiv", "escolta",
    "seguridad armada", "vigilante armado", "bombero", "piloto", "buzo",
    "soldador", "electricista de alta", "construccion", "construcción",
    "obra", "militar", "policia", "policía", "manejo de armas", "quimico",
    "químico", "conductor de carga", "transporte de valores",
)


# ---------------------------------------------------------------------------
# Interpretadores robustos de valores heterogéneos (bool | número | texto)
# ---------------------------------------------------------------------------
def _get(datos: dict, *keys: str, default: Any = None) -> Any:
    """Devuelve el primer alias presente y no vacío entre ``keys``."""
    for k in keys:
        if k in datos:
            v = datos.get(k)
            if v is not None and not (isinstance(v, str) and v.strip() == ""):
                return v
    return default


def _present(val: Any) -> bool:
    """True si el valor 'existe' (no None, no cadena vacía). El 0 SÍ cuenta:
    p.ej. dependientes=0 es información válida."""
    return val is not None and not (isinstance(val, str) and val.strip() == "")


def _truthy_text(val: Any) -> bool:
    """Interpreta un valor que puede llegar como bool, número o texto libre y
    responde si denota una condición PRESENTE/positiva.

    Ejemplos: True->True, "no"->False, "ninguna"->False, "no fumo"->False,
    "fumo 5"->True, "hipertensión"->True, 0->False, 3->True, "sí"->True.
    """
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, (list, tuple, set, dict)):
        return len(val) > 0
    s = str(val).strip().lower()
    if s in _NEG_FULL:
        return False
    if s in _AFF_FULL:
        return True
    # Cadena puramente numérica: "0" ya se filtró arriba, "5" -> presente.
    if s.replace(".", "", 1).isdigit():
        return float(s) != 0
    first = s.split()[0] if s.split() else ""
    # "no fumo", "ninguna condición", "nunca he..." -> ausencia.
    return first not in _NEG_FIRST_WORDS


def _as_bool(val: Any, default: bool = False) -> bool:
    """Booleano tolerante para campos sí/no (es_pep, ocupacion_riesgo...)."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    s = str(val).strip().lower()
    if s in _AFF_FULL:
        return True
    if s in _NEG_FULL:
        return False
    first = s.split()[0] if s.split() else ""
    return first not in _NEG_FIRST_WORDS


def _to_int(val: Any, default: int = 0) -> int:
    """Convierte a int de forma segura (acepta '2', 2.0, ' 3 ')."""
    if val is None:
        return default
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, (int, float)):
        return int(val)
    try:
        return int(float(str(val).strip().replace(",", ".")))
    except (ValueError, TypeError):
        return default


def _to_float(val: Any, default: float | None = None) -> float | None:
    """Convierte a float montos que pueden traer separadores ('2.500.000')."""
    if val is None:
        return default
    if isinstance(val, bool):
        return float(int(val))
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if s == "":
        return default
    # Limpia símbolos de moneda y separadores de miles comunes en COP.
    s = s.replace("$", "").replace("COP", "").replace(" ", "")
    s = s.replace(".", "").replace(",", "") if s.count(".") > 1 or s.count(",") > 1 else s
    s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# 1) Edad
# ---------------------------------------------------------------------------
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y")


def _parse_date(value: Any) -> date | None:
    if isinstance(value, (date, datetime)):
        return value.date() if isinstance(value, datetime) else value
    if not isinstance(value, str):
        return None
    s = value.strip()[:10]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _calc_edad(datos: dict, contexto: dict) -> int | None:
    """Edad a partir de fecha_nacimiento; si no hay, usa datos['age'].

    El 'hoy' puede fijarse con contexto['fecha_referencia'] para determinismo.
    """
    born = _parse_date(_get(datos, "fecha_nacimiento", "birth_date", "fecha_nac"))
    if born is not None:
        today = _parse_date(contexto.get("fecha_referencia")) or date.today()
        edad = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        # Guarda contra fechas absurdas (datos sucios).
        return edad if 0 <= edad <= 120 else None
    age = _get(datos, "age", "edad")
    return _to_int(age) if _present(age) else None


# ---------------------------------------------------------------------------
# 2) Etapa de vida  (edad + dependientes + estado civil)
# ---------------------------------------------------------------------------
_MARRIED_TOKENS = ("casad", "union", "unión", "conviv", "pareja")


def _en_pareja(estado_civil: Any) -> bool:
    if not _present(estado_civil):
        return False
    s = str(estado_civil).strip().lower()
    return any(t in s for t in _MARRIED_TOKENS)


def _etapa_vida(edad: int | None, dependientes: int, en_pareja: bool) -> str:
    """Segmenta el ciclo de vida combinando edad, dependientes y pareja.

    Heurística (rangos aproximados del mercado LATAM):
      - <30 sin familia            -> joven_independiente
      - <30 con hijos/pareja       -> joven_con_familia
      - 30-57 con dependientes     -> familia_consolidada
      - 30-57 sin dependientes     -> adulto_establecido
      - 58-64                      -> prejubilacion
      - >=65                       -> adulto_mayor
    Si la edad es desconocida se decide solo por señales familiares.
    """
    tiene_familia = dependientes > 0 or en_pareja
    if edad is None:
        return "familia_consolidada" if tiene_familia else "adulto_establecido"
    if edad >= 65:
        return "adulto_mayor"
    if edad >= 58:
        return "prejubilacion"
    if edad < 30:
        return "joven_con_familia" if tiene_familia else "joven_independiente"
    # 30-57
    return "familia_consolidada" if dependientes > 0 else "adulto_establecido"


# ---------------------------------------------------------------------------
# Detección de activos / negocio / viaje (soporta campo anidado o suelto)
# ---------------------------------------------------------------------------
def _tiene_vehiculo(datos: dict) -> bool:
    veh = datos.get("vehiculo")
    if isinstance(veh, dict) and any(_present(v) for v in veh.values()):
        return True
    if _truthy_text(veh):
        return True
    return any(_present(_get(datos, k)) for k in
               ("placa", "marca", "modelo_anio", "valor_comercial", "linea"))


def _es_propietario(datos: dict) -> bool:
    inm = datos.get("inmueble")
    if isinstance(inm, dict) and any(_present(v) for v in inm.values()):
        # Si declara tenencia, exige propietario; si no, basta con tener inmueble.
        ten = str(inm.get("tenencia", "")).strip().lower()
        return ten != "arrendatario"
    ten = str(_get(datos, "tenencia", default="")).strip().lower()
    if ten == "propietario":
        return True
    if ten == "arrendatario":
        return False
    return any(_present(_get(datos, k)) for k in
               ("valor_inmueble", "direccion_inmueble", "tipo_inmueble", "valor_contenidos"))


def _tiene_negocio(datos: dict) -> bool:
    if any(_present(_get(datos, k)) for k in
           ("nit", "razon_social", "actividad_negocio", "valor_activos")):
        return True
    origen = str(_get(datos, "origen_fondos", default="")).strip().lower()
    actividad = str(_get(datos, "actividad_economica", "ocupacion", default="")).strip().lower()
    return "negocio" in origen or "independiente" in actividad or "comerciante" in actividad


def _va_a_viajar(datos: dict, contexto: dict) -> bool:
    if _as_bool(contexto.get("viaja")):
        return True
    return any(_present(_get(datos, k)) for k in
               ("destino", "fecha_salida", "num_viajeros", "edades_viajeros"))


def _ocupacion_riesgosa(datos: dict) -> bool:
    """Ocupación de riesgo: bandera explícita o palabras clave en ocupación."""
    if _as_bool(_get(datos, "ocupacion_riesgo", "actividad_riesgo_alta", "trabajo_riesgo")):
        return True
    texto = " ".join(str(_get(datos, k, default="")) for k in
                     ("ocupacion", "actividad_economica", "actividad_negocio")).lower()
    return any(kw in texto for kw in _OCUP_RIESGO_KW)


# ---------------------------------------------------------------------------
# 3) Segmento de riesgo
# ---------------------------------------------------------------------------
def _segmento_riesgo(datos: dict, edad: int | None, tiene_vehiculo: bool,
                     ocup_riesgo: bool) -> tuple[str, list[str]]:
    """Puntúa el riesgo global sumando señales de salud, edad y auto.

    Puntos:  fumador +2 · enfermedades +2 · preexistencias +2 ·
             deportes de riesgo +1 · ocupación de riesgo +2 ·
             edad>=65 +1 (y +1 extra si >=75) ·
             [auto] edad<24 o >65 +1 · historial de siniestros +2
    Umbrales: 0-1 -> bajo | 2-3 -> medio | >=4 -> alto
    """
    puntos = 0
    motivos: list[str] = []
    if _truthy_text(_get(datos, "fumador")):
        puntos += 2
        motivos.append("fumador")
    if _truthy_text(_get(datos, "enfermedades")):
        puntos += 2
        motivos.append("enfermedades declaradas")
    if _truthy_text(_get(datos, "preexistencias", "preexistencias_viaje")):
        puntos += 2
        motivos.append("preexistencias")
    if _truthy_text(_get(datos, "deportes_riesgo", "deportes_viaje")):
        puntos += 1
        motivos.append("deportes de riesgo")
    if ocup_riesgo:
        puntos += 2
        motivos.append("ocupación de riesgo")
    if edad is not None:
        if edad >= 75:
            puntos += 2
            motivos.append("edad avanzada")
        elif edad >= 65:
            puntos += 1
            motivos.append("edad mayor")
    # Componente específico de auto (solo si hay vehículo).
    if tiene_vehiculo:
        if edad is not None and (edad < 24 or edad > 65):
            puntos += 1
            motivos.append("edad de conductor de mayor siniestralidad")
        if _truthy_text(_get(datos, "historial_siniestros")):
            puntos += 2
            motivos.append("historial de siniestros")

    segmento = "bajo" if puntos <= 1 else ("medio" if puntos <= 3 else "alto")
    return segmento, motivos


# ---------------------------------------------------------------------------
# 4) Capacidad de pago
# ---------------------------------------------------------------------------
# Fracción del ingreso mensual destinable a seguros (regla del negocio 5-8%,
# se usa el punto medio 6.5%).
_TASA_CAPACIDAD = 0.065
# Umbrales de ingreso mensual en COP para clasificar el nivel de capacidad.
_UMBRAL_BAJA = 2_500_000
_UMBRAL_ALTA = 7_000_000


def _capacidad(datos: dict) -> tuple[int | None, str]:
    ingresos = _to_float(_get(datos, "ingresos_mensuales", "ingresos", "income"))
    if ingresos is None or ingresos <= 0:
        # Sin dato de ingreso no se estima monto; nivel neutro 'media'.
        return None, "media"
    capacidad = int(round(ingresos * _TASA_CAPACIDAD))
    if ingresos < _UMBRAL_BAJA:
        nivel = "baja"
    elif ingresos < _UMBRAL_ALTA:
        nivel = "media"
    else:
        nivel = "alta"
    return capacidad, nivel


# ---------------------------------------------------------------------------
# 5) Necesidades detectadas
# ---------------------------------------------------------------------------
def _necesidades(datos: dict, contexto: dict, *, edad: int | None,
                 dependientes: int, en_pareja: bool, segmento: str,
                 tiene_vehiculo: bool, propietario: bool, negocio: bool,
                 viaja: bool, etapa: str) -> list[dict]:
    """Lista priorizada de tipos de seguro que la persona probablemente
    necesita, cada uno con su razón. prioridad: alta | media | baja."""
    nec: list[dict] = []
    tiene_familia = dependientes > 0 or en_pareja

    # Vida y Salud: protección del núcleo familiar (máxima prioridad).
    if tiene_familia:
        razon_fam = (f"tiene {dependientes} dependiente(s)" if dependientes > 0
                     else "vive en pareja")
        nec.append({"tipo": "vida", "razon": f"{razon_fam}; protege el ingreso familiar",
                    "prioridad": "alta"})
        nec.append({"tipo": "salud", "razon": f"{razon_fam}; cobertura médica del núcleo",
                    "prioridad": "alta"})
    else:
        # Sin familia: vida/accidentes de entrada, prioridad menor.
        nec.append({"tipo": "vida", "razon": "protección personal básica del ingreso",
                    "prioridad": "baja"})

    # Salud reforzada si hay señales de riesgo de salud aunque no haya familia.
    if not tiene_familia and segmento in ("medio", "alto"):
        nec.append({"tipo": "salud",
                    "razon": "perfil de salud con factores de riesgo declarados",
                    "prioridad": "media"})

    # Auto: tiene vehículo / placa.
    if tiene_vehiculo:
        nec.append({"tipo": "auto", "razon": "posee vehículo (placa/marca declarada)",
                    "prioridad": "alta"})

    # Hogar: es propietario de inmueble.
    if propietario:
        nec.append({"tipo": "hogar", "razon": "es propietario de un inmueble a proteger",
                    "prioridad": "media"})

    # PyME: tiene negocio / NIT.
    if negocio:
        nec.append({"tipo": "pyme", "razon": "tiene negocio propio (NIT/actividad comercial)",
                    "prioridad": "alta"})

    # Viaje: hay señales de viaje.
    if viaja:
        nec.append({"tipo": "viaje", "razon": "planea o realiza viajes",
                    "prioridad": "media"})

    # Accidentes personales: transversal, útil sobre todo para jóvenes/activos.
    nec.append({"tipo": "accidentes",
                "razon": "cobertura transversal de accidentes de bajo costo",
                "prioridad": "media" if not tiene_familia else "baja"})

    # Exequial / mayores: adultos mayores y prejubilación valoran exequial.
    if etapa in ("adulto_mayor", "prejubilacion") or (edad is not None and edad >= 58):
        nec.append({"tipo": "exequial",
                    "razon": "etapa de vida en que se valora la protección exequial familiar",
                    "prioridad": "media"})

    # Dedup por tipo conservando la mayor prioridad.
    orden = {"alta": 0, "media": 1, "baja": 2}
    mejor: dict[str, dict] = {}
    for item in nec:
        t = item["tipo"]
        if t not in mejor or orden[item["prioridad"]] < orden[mejor[t]["prioridad"]]:
            mejor[t] = item
    return sorted(mejor.values(), key=lambda i: orden[i["prioridad"]])


# ---------------------------------------------------------------------------
# 6) Productos recomendados  (necesidades + capacidad)
# ---------------------------------------------------------------------------
# Mapa tipo -> id de producto por nivel de capacidad (ids reales del
# catálogo data/market/catalogo_productos.json, priorizando Colsubsidio).
_PRODUCTO_POR_NECESIDAD = {
    "vida":       {"baja": "cs-vida-personal", "media": "cs-vida-personal", "alta": "cs-vida-ahorro"},
    "salud":      {"baja": "cs-asistencia-medica", "media": "salud-integral", "alta": "salud-global"},
    "auto":       {"baja": "cs-soat", "media": "cs-carro-todo-riesgo", "alta": "cs-carro-todo-riesgo"},
    "hogar":      {"baja": "cs-hogar-contenido", "media": "cs-hogar-contenido", "alta": "cs-hogar-contenido"},
    "viaje":      {"baja": "viaje-mundial", "media": "viaje-mundial", "alta": "viaje-mundial"},
    "pyme":       {"baja": "cs-colectivo-empresas", "media": "cs-colectivo-empresas", "alta": "pyme-multiriesgo"},
    "accidentes": {"baja": "cs-ap-exequial", "media": "cs-ap-exequial", "alta": "ap-personal"},
    "exequial":   {"baja": "cs-exequial-familiar", "media": "cs-exequial-familiar", "alta": "cs-exequial-familiar"},
}


def _productos_recomendados(necesidades: list[dict], nivel_capacidad: str) -> list[dict]:
    """Deriva ids de producto priorizados a partir de las necesidades y el
    nivel de capacidad de pago (elige el plan acorde al bolsillo)."""
    recs: list[dict] = []
    vistos: set[str] = set()
    for nec in necesidades:  # ya vienen ordenadas por prioridad
        tipo = nec["tipo"]
        pid = _PRODUCTO_POR_NECESIDAD.get(tipo, {}).get(nivel_capacidad)
        if pid and pid not in vistos:
            vistos.add(pid)
            recs.append({"tipo": tipo, "producto_id": pid, "prioridad": nec["prioridad"]})
    return recs


# ---------------------------------------------------------------------------
# 7) Propensión de compra
# ---------------------------------------------------------------------------
# Campos "clave" cuya presencia indica una conversación avanzada / lead cálido.
_CAMPOS_COMPLETITUD = (
    "nombre", "fecha_nacimiento", "sexo", "ciudad", "ocupacion",
    "ingresos_mensuales", "estado_civil", "dependientes", "email", "telefono",
)


def _propension_compra(datos: dict, contexto: dict) -> float:
    """Score 0..1 combinando completitud de datos, consentimiento y engagement.

    Pesos: completitud 0.40 · consentimiento 0.25 · cotización 0.20 ·
           engagement (nº de mensajes) 0.15.
    """
    # Completitud de datos.
    presentes = 0
    for c in _CAMPOS_COMPLETITUD:
        v = _get(datos, c, *(("nombre_completo",) if c == "nombre" else ()))
        # dependientes=0 cuenta como informado.
        if _present(v) or (c == "dependientes" and "dependientes" in datos):
            presentes += 1
    completitud = presentes / len(_CAMPOS_COMPLETITUD)

    # Consentimiento de habeas data (datos o contexto).
    consentimiento = _as_bool(_get(datos, "autoriza_habeas_data", "consent")) or \
        _as_bool(contexto.get("consintio")) or _as_bool(contexto.get("consent"))

    # ¿Ya cotizó?
    cotizo = _as_bool(contexto.get("cotizo")) or _as_bool(contexto.get("cotizado"))

    # Engagement por volumen de mensajes intercambiados (satura en ~8).
    num_msgs = _to_int(contexto.get("num_mensajes", contexto.get("mensajes", 0)))
    engagement = min(num_msgs / 8.0, 1.0) if num_msgs > 0 else 0.0

    score = (0.40 * completitud + 0.25 * (1.0 if consentimiento else 0.0)
             + 0.20 * (1.0 if cotizo else 0.0) + 0.15 * engagement)
    return round(max(0.0, min(1.0, score)), 3)


# ---------------------------------------------------------------------------
# 8) Banderas (underwriting / compliance)
# ---------------------------------------------------------------------------
def _banderas(datos: dict, *, edad: int | None, nivel_capacidad: str,
              ocup_riesgo: bool) -> list[str]:
    flags: list[str] = []
    if _as_bool(_get(datos, "es_pep", "pep")):
        flags.append("pep")  # SARLAFT / Decreto 1674
    if _truthy_text(_get(datos, "preexistencias", "enfermedades", "preexistencias_viaje")):
        flags.append("preexistencias")  # declaración de asegurabilidad
    if _truthy_text(_get(datos, "fumador")):
        flags.append("fumador")
    if ocup_riesgo:
        flags.append("alto_riesgo_ocupacional")
    if edad is not None and edad < 18:
        flags.append("menor_de_edad")
    if nivel_capacidad == "baja":
        flags.append("capacidad_baja")
    return flags


# ---------------------------------------------------------------------------
# 9) Resumen en lenguaje natural
# ---------------------------------------------------------------------------
_ETAPA_LABEL = {
    "joven_independiente": "joven independiente",
    "joven_con_familia": "joven con familia",
    "adulto_establecido": "adulto establecido",
    "familia_consolidada": "familia consolidada",
    "prejubilacion": "en etapa de prejubilación",
    "adulto_mayor": "adulto mayor",
}
_TIPO_LABEL = {
    "vida": "Vida", "salud": "Salud", "auto": "Auto", "hogar": "Hogar",
    "viaje": "Viaje", "pyme": "PyME", "accidentes": "Accidentes Personales",
    "exequial": "Exequial",
}


def _sexo_label(sexo: Any) -> str:
    s = str(sexo).strip().lower() if _present(sexo) else ""
    if s in ("f", "femenino", "mujer"):
        return "Mujer"
    if s in ("m", "masculino", "hombre"):
        return "Hombre"
    return "Persona"


def _resumen(sexo: Any, edad: int | None, etapa: str, dependientes: int,
             segmento: str, nivel_capacidad: str, necesidades: list[dict]) -> str:
    quien = _sexo_label(sexo)
    edad_txt = f"de {edad} años" if edad is not None else "(edad no informada)"
    etapa_txt = _ETAPA_LABEL.get(etapa, etapa)
    deps_txt = f" con {dependientes} dependiente(s)" if dependientes > 0 else ""
    top = [_TIPO_LABEL.get(n["tipo"], n["tipo"]) for n in necesidades[:2]]
    prioriza = " y ".join(top) if top else "una cobertura básica"
    return (f"{quien} {edad_txt}, {etapa_txt}{deps_txt}, riesgo {segmento}, "
            f"capacidad {nivel_capacidad}; prioriza {prioriza}.")


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
def build_profile(datos: dict, contexto: dict | None = None) -> dict:
    """Construye el hiper-perfil del cliente a partir de los datos recolectados.

    Args:
        datos: campos del cliente (ver data/market/requisitos_seguros.json).
            Todos opcionales; la función nunca falla por campos ausentes.
        contexto: señales de la conversación (num_mensajes, cotizo, consintio,
            viaja, fecha_referencia...). Opcional.

    Returns:
        dict con: edad, etapa_vida, segmento_riesgo, capacidad_pago_mensual_cop,
        nivel_capacidad, necesidades_detectadas, productos_recomendados,
        propension_compra, banderas, resumen_perfil (+ segmento_riesgo_motivos).
    """
    datos = datos or {}
    contexto = contexto or {}

    # --- señales base ---
    edad = _calc_edad(datos, contexto)
    dependientes = _to_int(_get(datos, "dependientes", "num_dependientes", default=0))
    en_pareja = _en_pareja(_get(datos, "estado_civil", "conductor_estado_civil"))
    tiene_vehiculo = _tiene_vehiculo(datos)
    propietario = _es_propietario(datos)
    negocio = _tiene_negocio(datos)
    viaja = _va_a_viajar(datos, contexto)
    ocup_riesgo = _ocupacion_riesgosa(datos)

    # --- dimensiones del perfil ---
    etapa = _etapa_vida(edad, dependientes, en_pareja)
    segmento, motivos_riesgo = _segmento_riesgo(datos, edad, tiene_vehiculo, ocup_riesgo)
    capacidad_cop, nivel_capacidad = _capacidad(datos)
    necesidades = _necesidades(
        datos, contexto, edad=edad, dependientes=dependientes, en_pareja=en_pareja,
        segmento=segmento, tiene_vehiculo=tiene_vehiculo, propietario=propietario,
        negocio=negocio, viaja=viaja, etapa=etapa)
    productos = _productos_recomendados(necesidades, nivel_capacidad)
    propension = _propension_compra(datos, contexto)
    banderas = _banderas(datos, edad=edad, nivel_capacidad=nivel_capacidad,
                         ocup_riesgo=ocup_riesgo)
    resumen = _resumen(_get(datos, "sexo", "genero"), edad, etapa, dependientes,
                       segmento, nivel_capacidad, necesidades)

    return {
        "edad": edad,
        "etapa_vida": etapa,
        "segmento_riesgo": segmento,
        "segmento_riesgo_motivos": motivos_riesgo,
        "capacidad_pago_mensual_cop": capacidad_cop,
        "nivel_capacidad": nivel_capacidad,
        "necesidades_detectadas": necesidades,
        "productos_recomendados": productos,
        "propension_compra": propension,
        "banderas": banderas,
        "resumen_perfil": resumen,
    }


# ---------------------------------------------------------------------------
# Casos de prueba manuales
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json

    casos = {
        "joven_soltero": (
            {
                "nombre": "Andrés Gómez", "fecha_nacimiento": "2001-03-10",
                "sexo": "M", "ciudad": "Medellín", "ocupacion": "Diseñador",
                "ingresos_mensuales": 2200000, "estado_civil": "Soltero",
                "dependientes": 0, "fumador": "no", "enfermedades": "ninguna",
                "deportes_riesgo": "no", "es_pep": False,
            },
            {"num_mensajes": 4, "cotizo": False},
        ),
        "familia_con_hijos_y_carro": (
            {
                "nombre": "Laura Restrepo", "fecha_nacimiento": "1988-11-22",
                "sexo": "F", "ciudad": "Bogotá", "ocupacion": "Ingeniera",
                "ingresos_mensuales": 8500000, "estado_civil": "Casada",
                "dependientes": 2, "fumador": "no", "preexistencias": "ninguna",
                "placa": "ABC123", "marca": "Mazda", "modelo_anio": 2021,
                "historial_siniestros": "no", "tenencia": "propietario",
                "valor_inmueble": 320000000, "autoriza_habeas_data": True,
                "email": "laura@mail.com", "telefono": "3001234567",
            },
            {"num_mensajes": 9, "cotizo": True, "consintio": True},
        ),
        "adulto_mayor_fumador": (
            {
                "nombre": "Jorge Peña", "fecha_nacimiento": "1952-06-01",
                "sexo": "M", "ciudad": "Cali", "ocupacion": "Pensionado",
                "ingresos_mensuales": 1500000, "estado_civil": "Viudo",
                "dependientes": 0, "fumador": "sí, 10 al día",
                "enfermedades": "hipertensión", "preexistencias": "diabetes",
                "es_pep": False,
            },
            {"num_mensajes": 6, "cotizo": False},
        ),
    }

    for etiqueta, (d, c) in casos.items():
        print(f"\n===== {etiqueta} =====")
        print(json.dumps(build_profile(d, c), ensure_ascii=False, indent=2))
