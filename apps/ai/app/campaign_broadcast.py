"""Envío masivo de WhatsApp para una campaña — recibe un segmento de leads YA
RESUELTO por NestJS (ver apps/backend/src/modules/campaigns/campaigns.service.ts
`send()`, que filtra por intent + consentimiento) y hace el envío real, que
solo este servicio sabe hacer (whatsapp_gateway.py).

Llamada servicio-a-servicio (X-Service-Key), fire-and-forget del lado de
NestJS: este endpoint encola en BackgroundTasks y responde de inmediato.
Rate-limit fijo de `CAMPAIGN_SEND_DELAY_SECONDS` entre envíos — el gateway
Baileys reusado NO es oficial (riesgo real de ban por detección de bulk, no
un rate-limit de API), ver docs/PLAN.md. Por cada resultado se reporta de
vuelta a NestJS (`backend_client.update_campaign_send`, PATCH individual, no
batch) para que el `CampaignSend` quede ENVIADO/FALLIDO; si ese callback
nunca llega (proceso caído a mitad de camino), el barrido de
`CampaignsService.reconcileStalePending` (cron cada 15 min, >90 min) lo
reconcilia solo, nunca queda colgado en PENDIENTE para siempre.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from . import backend_client, whatsapp_gateway
from .config import CAMPAIGN_BROADCAST_MAX, CAMPAIGN_SEND_DELAY_SECONDS, SERVICE_API_KEY

log = logging.getLogger("seguria.campaign_broadcast")
router = APIRouter()


def _require_service(x_service_key: str = Header(default="")) -> None:
    if x_service_key != SERVICE_API_KEY:
        raise HTTPException(403, "Se requiere API key de servicio (header X-Service-Key)")


class BroadcastSend(BaseModel):
    send_id: str
    phone: str
    message: str


class BroadcastRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant dueño de la campaña (para el callback)")
    sends: list[BroadcastSend] = Field(..., description="Destinatarios ya resueltos por NestJS")


def _run_broadcast(tenant_id: str, sends: list[BroadcastSend]) -> None:
    for i, s in enumerate(sends):
        if i > 0:
            time.sleep(CAMPAIGN_SEND_DELAY_SECONDS)
        ok = whatsapp_gateway.enviar_whatsapp(s.phone, s.message)
        backend_client.update_campaign_send(
            tenant_id, s.send_id, "ENVIADO" if ok else "FALLIDO",
            error=None if ok else "el gateway de WhatsApp no confirmó el envío")
    log.info("broadcast de campaña terminado: %d envíos (tenant=%s)", len(sends), tenant_id)


@router.post("/api/marketing/campaigns/broadcast", dependencies=[Depends(_require_service)])
def broadcast(req: BroadcastRequest, background_tasks: BackgroundTasks) -> dict:
    """Encola el envío y responde YA — el resultado real llega por callback
    PATCH a NestJS, uno por uno, a medida que se procesa cada destinatario."""
    if len(req.sends) > CAMPAIGN_BROADCAST_MAX:
        raise HTTPException(
            400, f"máximo {CAMPAIGN_BROADCAST_MAX} envíos por llamada, llegaron {len(req.sends)}")
    if not req.sends:
        return {"accepted": 0}
    background_tasks.add_task(_run_broadcast, req.tenant_id, req.sends)
    return {"accepted": len(req.sends)}
