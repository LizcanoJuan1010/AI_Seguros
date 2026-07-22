"""Export dashboards, questions, models y metrics del Metabase del cliente vía API REST.

Uso:
    export METABASE_URL="https://metabase.cliente.com"
    export METABASE_USERNAME="tu@email.com"
    export METABASE_PASSWORD="..."          # o METABASE_API_KEY si tienes una
    .venv/bin/python scripts/metabase_export.py [--out metabase_export]

Baja todo lo que tu usuario puede ver: árbol de colecciones, cards (preguntas
y models, con su dataset_query — SQL nativo o MBQL), dashboards con sus
dashcards, y metadatos de las bases de datos conectadas. No modifica nada en
el servidor (solo GETs).
"""

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

import requests

DEFAULT_URL = "https://long-bound.metabaseapp.com"


def slugify(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)
    return safe.strip().replace(" ", "_")[:80] or "sin_nombre"


class MetabaseClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def login(self):
        api_key = os.environ.get("METABASE_API_KEY")
        if api_key:
            self.session.headers["x-api-key"] = api_key
            return
        user = os.environ.get("METABASE_USERNAME") or input("Email de Metabase: ").strip()
        password = os.environ.get("METABASE_PASSWORD") or getpass.getpass(
            "Contraseña de Metabase (no se muestra al escribir): "
        )
        resp = self.session.post(
            f"{self.base_url}/api/session",
            json={"username": user, "password": password},
            timeout=30,
        )
        if resp.status_code == 401:
            sys.exit(
                "Login rechazado (401): email o contraseña incorrectos. Si entras "
                "con Google, crea una contraseña en Account settings primero."
            )
        resp.raise_for_status()
        self.session.headers["X-Metabase-Session"] = resp.json()["id"]

    def get(self, path: str, **params):
        resp = self.session.get(f"{self.base_url}/api{path}", params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="metabase_export")
    args = ap.parse_args()

    url = os.environ.get("METABASE_URL", DEFAULT_URL)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    mb = MetabaseClient(url)
    mb.login()

    databases = mb.get("/database")
    db_list = databases["data"] if isinstance(databases, dict) else databases
    (out / "databases.json").write_text(json.dumps(db_list, indent=2, ensure_ascii=False))
    print(f"{len(db_list)} bases de datos conectadas")

    collections = mb.get("/collection")
    (out / "collections.json").write_text(json.dumps(collections, indent=2, ensure_ascii=False))
    coll_names = {c["id"]: c["name"] for c in collections}
    print(f"{len(collections)} colecciones visibles")

    cards = mb.get("/card")
    print(f"{len(cards)} cards (preguntas + models) visibles")
    cards_dir = out / "cards"
    cards_dir.mkdir(exist_ok=True)
    for card in cards:
        coll = slugify(coll_names.get(card.get("collection_id"), "root"))
        coll_dir = cards_dir / coll
        coll_dir.mkdir(exist_ok=True)
        fname = f"{card['id']}_{slugify(card['name'])}.json"
        (coll_dir / fname).write_text(json.dumps(card, indent=2, ensure_ascii=False))

    dash_dir = out / "dashboards"
    dash_dir.mkdir(exist_ok=True)
    dash_index = mb.get("/dashboard")
    if isinstance(dash_index, dict):
        dash_index = dash_index.get("data", [])
    print(f"{len(dash_index)} dashboards visibles")
    for d in dash_index:
        try:
            full = mb.get(f"/dashboard/{d['id']}")
        except requests.HTTPError as e:
            print(f"  dashboard {d['id']} ({d.get('name')}): {e}")
            continue
        coll = slugify(coll_names.get(full.get("collection_id"), "root"))
        coll_dir = dash_dir / coll
        coll_dir.mkdir(exist_ok=True)
        fname = f"{full['id']}_{slugify(full['name'])}.json"
        (coll_dir / fname).write_text(json.dumps(full, indent=2, ensure_ascii=False))

    native = sum(
        1 for c in cards if (c.get("dataset_query") or {}).get("type") == "native"
    )
    print(f"\nListo: export en {out.resolve()}")
    print(f"  cards con SQL nativo: {native} / {len(cards)} (el resto es MBQL)")


if __name__ == "__main__":
    main()
