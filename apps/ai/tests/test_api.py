"""Suite de pruebas de la API Tequendama (FastAPI TestClient).

Cubre: catálogo, cotizador (casos borde), documentos, auth de servicio/gerente,
path traversal, insights y motor proactivo.

Corre contra PostgreSQL (compose en localhost:5432) en un esquema aislado
`seguria_test` que conftest crea al inicio y DROPa al final:
    DATABASE_URL=postgresql://seguria:seguria@localhost:5432/seguria \\
        .venv/bin/python -m pytest tests/ -q
Sin Postgres, conftest salta la suite con un motivo claro (no falla).
"""
import pytest
from fastapi.testclient import TestClient

# El esquema de test, las API keys y DATABASE_URL los fija conftest.py ANTES de
# importar `app.*`; el esquema `seguria_test` (tablas + seeds) lo prepara su fixture
# de sesión autouse. Aquí solo construimos el cliente HTTP.
from app.main import app  # noqa: E402

client = TestClient(app)
MGR = {"X-API-Key": "test-mgr"}
SVC = {"X-Service-Key": "test-svc"}


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_countries_and_products():
    assert len(client.get("/api/countries").json()) == 12
    prods = client.get("/api/products?country=CO&tipo=vida").json()
    assert prods and all("CO" in p["paises"] and p["tipo"] == "vida" for p in prods)


def test_quote_basic():
    r = client.post("/api/quotes", json={"country": "CO", "tipo": "vida", "age": 34,
                                         "extras": {"dependientes": 2}})
    assert r.status_code == 200
    ops = r.json()["opciones"]
    assert ops and all(o["moneda"] == "COP" for o in ops)
    assert ops[0]["prima_mensual_local"] > ops[0]["prima_mensual_usd"]  # COP > USD


def test_quote_invalid_country():
    assert client.post("/api/quotes", json={"country": "XX"}).status_code == 400


def test_quote_travel_defaults_days():
    o = client.post("/api/quotes", json={"country": "PA", "tipo": "viaje", "age": 30}).json()["opciones"][0]
    assert o["breakdown"]["dias_viaje"] == 15
    assert o["breakdown"]["dias_asumidos"] is True


def test_age_extrapolation_uses_contiguous_band():
    o = client.post("/api/quotes", json={"country": "MX", "tipo": "auto", "age": 90}).json()["opciones"][0]
    # 90 años debe caer en la banda superior 66-80, no en 18-25 (mayor factor)
    assert o["breakdown"]["factor_edad"]["banda"].startswith("66-80")


def test_document_generation_and_download():
    qid = client.post("/api/quotes", json={"country": "CO", "tipo": "salud", "age": 40}).json()["opciones"][0]["quote_id"]
    doc = client.post(f"/api/quotes/{qid}/document").json()
    assert doc["download_url"].endswith(".pdf")
    pdf = client.get(doc["download_url"])
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert len(pdf.content) > 1000


def test_document_not_found():
    assert client.post("/api/quotes/999999/document").status_code == 404


def test_path_traversal_blocked():
    for evil in ("../app/config.py", "..%2Fapp%2Fconfig.py", "noexiste.pdf"):
        assert client.get(f"/api/documents/{evil}").status_code == 404


def test_service_auth_required():
    assert client.get("/api/roles/+573001112233").status_code == 403
    assert client.get("/api/roles/+573001112233", headers=SVC).json()["role"] == "cliente"
    assert client.post("/api/leads", json={"phone": "x"}).status_code == 403
    assert client.post("/api/conversations", json={"phone": "x", "message": "hi"}).status_code == 403
    assert client.get("/api/proactive/+57300", ).status_code == 403


def test_manager_auth_required():
    assert client.get("/api/insights/summary").status_code == 403
    assert client.get("/api/proactive").status_code == 403
    data = client.get("/api/insights/summary", headers=MGR).json()
    assert "kpis" in data and "funnel" in data


def test_chat_degrades_without_llm(monkeypatch):
    monkeypatch.setattr("app.agent_core.DEEPSEEK_API_KEY", "")
    r = client.post("/api/chat", json={"session_id": "t1", "message": "hola"})
    assert r.status_code == 200
    assert r.json()["error"] == "llm_no_configurado"


def test_xss_name_stored_but_not_reflected_raw():
    # El nombre malicioso se almacena; la defensa XSS es el escape en el render (SPA).
    payload = '<img src=x onerror=alert(1)>'
    client.post("/api/leads", headers=SVC,
                json={"phone": "+57300999", "name": payload, "stage": "descubrimiento"})
    leads = client.get("/api/insights/leads", headers=MGR).json()
    assert any(l["name"] == payload for l in leads)  # se guarda tal cual; el SPA lo escapa


def test_memory_isolation_por_tenant():
    """Aislamiento de dos ejes (patrón Paloma): un recuerdo guardado bajo el tenant A
    NO es visible desde el tenant B aunque compartan el mismo user_id. Sin DATABASE_URL
    esto ejercita el fallback en-proceso, también particionado por (tenant_id, user_id)."""
    import asyncio

    from app import memory

    async def _scenario():
        await memory.add_memory("u1", "El cliente prefiere seguro de vida", "interes",
                                tenant_id="tenantA")
        ctx_a = await memory.get_memory_context("u1", tenant_id="tenantA")
        ctx_b = await memory.get_memory_context("u1", tenant_id="tenantB")
        hits_b = await memory.search_memories("u1", "vida", tenant_id="tenantB")
        return ctx_a, ctx_b, hits_b

    ctx_a, ctx_b, hits_b = asyncio.run(_scenario())
    assert "seguro de vida" in ctx_a   # visible en su propio tenant
    assert ctx_b == ""                 # NO se filtra a otro tenant con el mismo user_id
    assert hits_b == []                # la búsqueda tampoco cruza tenants


def test_resolve_identity_jwt_vs_fallback():
    """El tenant y el rol salen del JWT del login (patrón Paloma); sin token válido
    caen al fallback `X-Tenant-Id`/tenant demo + `manager_key`."""
    import time

    from app import config
    from app.auth import _jwt_encode, decode_token, resolve_identity

    claims = {"sub": "u1", "email": "g@x", "name": "G", "role": "GERENTE",
              "teamId": "22222222-2222-2222-2222-222222222222", "type": "access",
              "exp": int(time.time()) + 3600}
    token = _jwt_encode(claims, config.JWT_SECRET)

    # (a) token válido de gerente → tenant del teamId + rol gerente
    assert decode_token(token) is not None
    assert resolve_identity(f"Bearer {token}", None, None) == \
        ("22222222-2222-2222-2222-222222222222", "gerente")

    # (b) sin token → fallback al header X-Tenant-Id y rol cliente
    assert resolve_identity(None, "11111111-1111-1111-1111-111111111111", None) == \
        ("11111111-1111-1111-1111-111111111111", "cliente")

    # (c) fallback: manager_key correcta eleva a gerente; tenant demo si no hay header
    assert resolve_identity(None, None, "test-mgr") == \
        (config.DEMO_TENANT_ID, "gerente")

    # (d) firma inválida / token corrupto → se ignora y cae al fallback
    assert resolve_identity("Bearer not.a.jwt", None, None) == \
        (config.DEMO_TENANT_ID, "cliente")

    # (e) claims sin role privilegiado → cliente aunque el token sea válido
    cli = dict(claims, role="AGENTE")
    cli_token = _jwt_encode(cli, config.JWT_SECRET)
    assert resolve_identity(f"Bearer {cli_token}", None, None) == \
        ("22222222-2222-2222-2222-222222222222", "cliente")


def test_sessions_listing_requires_staff():
    """El historial GLOBAL de conversaciones es vista de auditoría: sin Bearer de
    staff responde 403 (el cliente anónimo no debe ver sesiones ajenas)."""
    import time

    from app import config
    from app.auth import _jwt_encode, is_staff_token

    assert client.get("/api/assistant/sessions").status_code == 403
    assert client.get("/api/assistant/sessions",
                      headers={"Authorization": "Bearer not.a.jwt"}).status_code == 403

    # Un vendedor (AGENTE) sí es staff: puede auditar conversaciones.
    claims = {"sub": "u2", "email": "v@x", "name": "V", "role": "AGENTE",
              "teamId": "22222222-2222-2222-2222-222222222222", "type": "access",
              "exp": int(time.time()) + 3600}
    token = _jwt_encode(claims, config.JWT_SECRET)
    assert is_staff_token(f"Bearer {token}") is True
    r = client.get("/api/assistant/sessions",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_chat_identity_prefers_device_id():
    """La identidad del turno ancla al device_id (cuenta anónima durable del
    navegador) por encima del session_id; el teléfono real sigue mandando."""
    from app.db import get_conn

    r = client.post("/api/chat", json={"session_id": "sess_efimera",
                                       "message": "hola",
                                       "device_id": "dev_abc123"})
    assert r.status_code == 200

    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT phone FROM conversations WHERE phone LIKE 'web:%' "
            "ORDER BY id DESC LIMIT 5").fetchall()
    finally:
        conn.close()
    users = {row["phone"] for row in rows}
    assert "web:dev_abc123" in users
    assert "web:sess_efimera" not in users


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
