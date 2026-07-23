"""Seguro embebido (quote & bind) para aliados B2B2C — distribución en el
punto de compra (caso estrella del paper de McKinsey).

Un e-commerce/banco aliado integra dos llamadas en su checkout:
  POST /api/embedded/quote    → prima al instante (cotizador determinista)
  POST /api/embedded/checkout → emite la póliza real (backend NestJS) en un paso

Auth por API key de partner (`PARTNER_API_KEYS`). El underwriting aplica igual
que en el chat: solo riesgos simples se auto-emiten; lo demás se refiere.
La página `/embed` del frontend usa esta API y es embebible por iframe.
"""
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import underwriting
from .config import BACKEND_URL, PARTNER_API_KEYS
from .db import COUNTRY_NAMES, get_conn
from .documents import build_policy_pdf
from .quoting import recommend

log = logging.getLogger("seguria.embedded")
router = APIRouter()


def _check_partner(key: str) -> None:
    if (key or "").strip() not in PARTNER_API_KEYS:
        raise HTTPException(403, "partner_key inválida: solicita acceso de aliado")


class EmbeddedQuoteRequest(BaseModel):
    partner_key: str = Field(..., description="API key del aliado")
    tipo: str = Field(..., description="vida|salud|auto|hogar|viaje|accidentes|...")
    country: str = Field("CO", description="Código ISO-2")
    age: int | None = None
    sum_assured_usd: float | None = None
    valor_bien_usd: float | None = Field(None, description="Valor del bien (auto/hogar)")
    dias_viaje: int | None = None


@router.post("/api/embedded/quote")
def embedded_quote(req: EmbeddedQuoteRequest) -> dict:
    """Prima al instante para mostrar en el checkout del aliado."""
    _check_partner(req.partner_key)
    country = req.country.upper()
    if country not in COUNTRY_NAMES:
        raise HTTPException(400, f"país no soportado: {country}")
    extras: dict[str, Any] = {}
    if req.valor_bien_usd:
        extras["valor_bien_usd"] = req.valor_bien_usd
    if req.dias_viaje:
        extras["dias_viaje"] = req.dias_viaje
    conn = get_conn()
    try:
        options = recommend(conn, country=country, tipo=req.tipo.lower(),
                            age=req.age, sum_assured_usd=req.sum_assured_usd,
                            budget_monthly_usd=None, extras=extras, max_options=1)
    finally:
        conn.close()
    if not options:
        raise HTTPException(404, f"sin productos de {req.tipo} en {country}")
    o = options[0]
    o.pop("breakdown", None)
    return {"opcion": o,
            "mensaje": f"Protege tu compra por {o['prima_mensual_local']:,.0f} "
                       f"{o['moneda']}/{'viaje' if o['periodicidad'] == 'por viaje' else 'mes'}"}


class EmbeddedCustomer(BaseModel):
    fullName: str
    documentId: str
    documentType: str = "CC"
    email: str | None = None
    phone: str | None = None


class EmbeddedCheckoutRequest(BaseModel):
    partner_key: str
    tipo: str = Field(..., description="Tipo de seguro (vida|auto|salud)")
    monthly_premium_cop: float = Field(..., gt=0)
    customer: EmbeddedCustomer
    consent_data: bool = Field(..., description="Habeas data (Ley 1581/2012)")
    coverage: dict[str, Any] = Field(default_factory=dict)
    partner_name: str | None = Field(None, description="Nombre del aliado (para auditoría)")


@router.post("/api/embedded/checkout")
def embedded_checkout(req: EmbeddedCheckoutRequest) -> dict:
    """Bind en un paso: underwriting → emisión real vía el backend NestJS."""
    _check_partner(req.partner_key)
    if not req.consent_data:
        raise HTTPException(400, "se requiere el consentimiento de habeas data")

    # Mismo underwriting del chat (sin perfil: aplican las reglas de prima).
    uw = underwriting.evaluate(None, insurance_type=req.tipo,
                               monthly_premium_cop=req.monthly_premium_cop)
    if uw["decision"] != underwriting.AUTO_APPROVE:
        return {"referred": True, "underwriting": uw,
                "mensaje": "Esta solicitud requiere revisión de un asesor; "
                           "te contactaremos en menos de 24 horas."}

    coverage = {**req.coverage,
                "origen": "embedded",
                **({"partner": req.partner_name} if req.partner_name else {}),
                "underwriting": {k: uw[k] for k in
                                 ("decision", "reasons", "segmento_riesgo",
                                  "umbral_autoemision_cop")}}
    payload = {
        "customer": {k: v for k, v in req.customer.model_dump().items() if v},
        "consentData": True,
        "insuranceType": req.tipo.strip().upper(),
        "monthlyPremiumCop": round(req.monthly_premium_cop, 2),
        "coverage": coverage,
        "payment": {"method": "embedded", "reference": "partner-checkout"},
        "leadId": None,
    }
    try:
        import requests
        resp = requests.post(f"{BACKEND_URL}/api/v1/checkout", json=payload, timeout=8)
        resp.raise_for_status()
        policy = resp.json() or {}
    except Exception as exc:
        log.warning("checkout embebido falló: %s", exc)
        raise HTTPException(502, "el sistema de emisión no está disponible; reintenta")

    download_url = None
    try:
        path = build_policy_pdf({**policy, "aseguradora": coverage.get("aseguradora")},
                                payload["customer"], coverage)
        download_url = f"/api/documents/{Path(path).name}"
    except Exception:
        log.exception("no se pudo generar el PDF de la póliza embebida")

    return {"policyNumber": policy.get("policyNumber"),
            "status": policy.get("status"),
            "startDate": policy.get("startDate"),
            "endDate": policy.get("endDate"),
            "download_url": download_url,
            "underwriting": uw}
