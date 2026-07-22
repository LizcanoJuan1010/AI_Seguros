"""Cliente REST mínimo de Metabase (adaptado de reference/metabase_export_reference.py).

Opcional: solo se activa si METABASE_URL y METABASE_API_KEY están configurados.
Permite a la skill de gerentes listar dashboards y ejecutar cards guardadas.
"""
from typing import Any

import requests

from .config import METABASE_API_KEY, METABASE_URL


class MetabaseClient:
    def __init__(self, url: str = METABASE_URL, api_key: str = METABASE_API_KEY):
        self.url = url.rstrip("/")
        self.headers = {"x-api-key": api_key}

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.headers["x-api-key"])

    def _get(self, path: str) -> Any:
        r = requests.get(f"{self.url}/api/{path}", headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()

    def list_dashboards(self) -> list[dict]:
        data = self._get("dashboard")
        return [{"id": d["id"], "name": d["name"],
                 "url": f"{self.url}/dashboard/{d['id']}"} for d in data]

    def run_card(self, card_id: int) -> Any:
        r = requests.post(f"{self.url}/api/card/{card_id}/query/json",
                          headers=self.headers, timeout=60)
        r.raise_for_status()
        return r.json()
