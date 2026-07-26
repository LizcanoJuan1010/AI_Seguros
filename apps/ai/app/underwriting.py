"""Underwriting semiautónomo: la decisión de emisión del pipeline agéntico.

Cierra el ciclo intake (`intake.py`) → perfil (`profiling.py`) → pricing
(`quoting.py`) con una decisión determinista y auditable ANTES de emitir:

  AUTO_APPROVE — riesgo simple: la póliza se emite sin humano en el chat.
  REFER        — señal de suscripción/SARLAFT: escala a un gerente (alerta en
                 el panel) y NO se emite hasta la aprobación humana.
  DECLINE      — no asegurable en este canal (ej. menor de edad).

Las reglas son explícitas y quedan registradas (razones + umbral) en
`Quote.coverage.underwriting` vía el checkout. El LLM nunca decide.
"""
from typing import Any

AUTO_APPROVE = "AUTO_APPROVE"
REFER = "REFER"
DECLINE = "DECLINE"

# Prima mensual (COP) máxima para auto-emitir, por tipo de seguro. Por encima
# del umbral la solicitud pasa a suscripción humana.
PREMIUM_REFER_COP = {
    "VIDA": 400_000,
    "SALUD": 600_000,
    "AUTO": 800_000,
    "HOGAR": 500_000,
    "VIAJE": 1_000_000,
    "PYME": 1_500_000,
    "ACCIDENTES": 300_000,
}
DEFAULT_PREMIUM_REFER_COP = 500_000

# Edad desde la cual un seguro de vida requiere suscripción humana.
LIFE_REFER_AGE = 70

# Edad máxima de ingreso para productos COLECTIVOS (aceptación garantizada):
# sin suscripción individual, esta es la única palanca contra selección
# adversa que queda del lado de underwriting (las otras son estructurales del
# producto: carencias, tope de suma asegurada — ver
# Nota_estrategica_Seguros_Colsubsidio.pdf §1).
COLLECTIVE_MAX_ENTRY_AGE = 70


def evaluate(perfil: dict[str, Any] | None, *, insurance_type: str,
             monthly_premium_cop: float, modalidad: str = "individual") -> dict[str, Any]:
    """Evalúa la solicitud y devuelve `{decision, reasons, ...}` auditable.

    `perfil` es la salida de `profiling.build_profile` (puede ser None si no
    hay datos: en ese caso solo aplican las reglas de prima).

    `modalidad` (del producto, ver `products.modalidad`/catálogo):
    - "colectiva": póliza colectiva con Colsubsidio como tomador y el cliente
      como asegurado, aceptación GARANTIZADA — no hay suscripción individual
      ni declaración del estado del riesgo (Art. 1058 C. Co. neutralizado).
      Se salta TODA la evaluación de riesgo individual de abajo; solo se
      controla la edad máxima de ingreso.
    - "asesor": producto de alta fricción (auto todo riesgo, vida con
      ahorro...) que NO es autogestionable — declina por este canal siempre,
      independiente del perfil.
    - "individual" (default): flujo de suscripción de hoy, sin cambios.
    """
    perfil = perfil or {}
    tipo = (insurance_type or "").strip().upper() or "VIDA"
    try:
        prima = round(float(monthly_premium_cop or 0), 2)
    except (TypeError, ValueError):
        prima = 0.0
    banderas = set(perfil.get("banderas") or [])
    segmento = perfil.get("segmento_riesgo") or "medio"
    edad = perfil.get("edad")
    umbral = PREMIUM_REFER_COP.get(tipo, DEFAULT_PREMIUM_REFER_COP)

    if "menor_de_edad" in banderas:
        return {"decision": DECLINE, "tipo": tipo, "prima_cop": prima,
                "reasons": ["el tomador es menor de edad: no asegurable en este canal"],
                "segmento_riesgo": segmento}

    if modalidad == "asesor":
        return {"decision": DECLINE, "tipo": tipo, "prima_cop": prima,
                "segmento_riesgo": segmento,
                "reasons": ["este producto requiere asesoría humana (alta fricción o "
                           "decisión financiera compleja): no se ofrece por este "
                           "canal autogestionado"]}

    if modalidad == "colectiva":
        if edad is not None and edad >= COLLECTIVE_MAX_ENTRY_AGE:
            return {"decision": DECLINE, "tipo": tipo, "prima_cop": prima,
                    "segmento_riesgo": segmento,
                    "reasons": [f"edad {edad}: supera la edad máxima de ingreso "
                               f"({COLLECTIVE_MAX_ENTRY_AGE} años) de este producto colectivo"]}
        return {"decision": AUTO_APPROVE, "tipo": tipo, "prima_cop": prima,
               "umbral_autoemision_cop": None, "segmento_riesgo": segmento,
               "reasons": ["póliza colectiva con aceptación garantizada: sin "
                          "suscripción individual ni declaración de riesgo"]}

    reasons: list[str] = []
    if "pep" in banderas:
        reasons.append("cliente PEP: revisión SARLAFT obligatoria")
    if "preexistencias" in banderas and tipo in ("VIDA", "SALUD"):
        reasons.append("preexistencias declaradas: requiere análisis de "
                       "asegurabilidad (Art. 1058 C. de Comercio)")
    if segmento == "alto":
        motivos = ", ".join((perfil.get("segmento_riesgo_motivos") or [])[:3])
        reasons.append(f"segmento de riesgo alto ({motivos or 'múltiples señales'})")
    if edad is not None and tipo == "VIDA" and edad >= LIFE_REFER_AGE:
        reasons.append(f"edad {edad} en seguro de vida: suscripción humana "
                       f"desde los {LIFE_REFER_AGE} años")
    if prima > umbral:
        reasons.append(f"prima {prima:,.0f} COP/mes supera el umbral de "
                       f"auto-emisión para {tipo.lower()} ({umbral:,.0f} COP)")

    decision = REFER if reasons else AUTO_APPROVE
    return {
        "decision": decision,
        "tipo": tipo,
        "prima_cop": prima,
        "umbral_autoemision_cop": umbral,
        "segmento_riesgo": segmento,
        "reasons": reasons or ["riesgo simple dentro de todos los umbrales de auto-emisión"],
    }
