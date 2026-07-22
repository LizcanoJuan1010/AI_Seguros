"""
PipeOs - Cliente para WhatsApp Business API oficial (Cloud API).
Alternativa segura a Evolution API. Sin riesgo de ban.
Proveedor recomendado: 360dialog.com como BSP.
Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
"""
import httpx
from config import WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN

_BASE_URL = "https://graph.facebook.com/v21.0"


class WhatsAppOfficialClient:
    """Cliente async para WhatsApp Cloud API."""

    def __init__(self):
        self.phone_number_id = WHATSAPP_PHONE_NUMBER_ID
        self.access_token = WHATSAPP_ACCESS_TOKEN
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.phone_number_id and self.access_token)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def send_text(self, to: str, body: str) -> dict:
        """Enviar mensaje de texto.
        Args:
            to: Numero destino con codigo de pais (ej: 573001234567)
            body: Texto del mensaje
        """
        client = self._get_client()
        resp = await client.post(
            f"/{self.phone_number_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": body},
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def send_template(
        self, to: str, template_name: str, language: str = "es",
        components: list[dict] | None = None,
    ) -> dict:
        """Enviar mensaje con template aprobado por Meta."""
        client = self._get_client()
        body: dict = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
            },
        }
        if components:
            body["template"]["components"] = components
        resp = await client.post(f"/{self.phone_number_id}/messages", json=body)
        resp.raise_for_status()
        return resp.json()

    async def send_image(self, to: str, image_url: str, caption: str = "") -> dict:
        """Enviar imagen con caption opcional."""
        client = self._get_client()
        media: dict = {"link": image_url}
        if caption:
            media["caption"] = caption
        resp = await client.post(
            f"/{self.phone_number_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "image",
                "image": media,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def send_document(
        self, to: str, document_url: str, filename: str, caption: str = ""
    ) -> dict:
        """Enviar documento (PDF, etc)."""
        client = self._get_client()
        doc: dict = {"link": document_url, "filename": filename}
        if caption:
            doc["caption"] = caption
        resp = await client.post(
            f"/{self.phone_number_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "document",
                "document": doc,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def mark_read(self, message_id: str) -> dict:
        """Marcar mensaje como leido."""
        client = self._get_client()
        resp = await client.post(
            f"/{self.phone_number_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def send_interactive_buttons(
        self, to: str, body_text: str, buttons: list[dict],
        header: str = "", footer: str = "",
    ) -> dict:
        """Enviar mensaje interactivo con botones (max 3)."""
        client = self._get_client()
        action_buttons = []
        for i, btn in enumerate(buttons[:3]):
            action_buttons.append({
                "type": "reply",
                "reply": {
                    "id": btn.get("id", f"btn_{i}"),
                    "title": btn["title"][:20],
                },
            })
        interactive: dict = {
            "type": "button",
            "body": {"text": body_text},
            "action": {"buttons": action_buttons},
        }
        if header:
            interactive["header"] = {"type": "text", "text": header}
        if footer:
            interactive["footer"] = {"text": footer}
        resp = await client.post(
            f"/{self.phone_number_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "interactive",
                "interactive": interactive,
            },
        )
        resp.raise_for_status()
        return resp.json()


# Singleton
whatsapp_official_client = WhatsAppOfficialClient()
