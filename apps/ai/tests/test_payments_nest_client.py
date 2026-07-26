"""Unit tests: AI payments es cliente Nest (sin Polar HTTP / token)."""
from unittest.mock import MagicMock, patch

import pytest

from app import payments

pytestmark = pytest.mark.unit


class _FakeResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


@pytest.fixture
def conn():
    """Conn mínima en memoria: usa mocks de execute/commit."""
    store: dict = {}

    class Row(dict):
        pass

    def execute(sql, params=None):
        params = params or ()
        cur = MagicMock()
        sql_u = " ".join(sql.split()).upper()
        if sql_u.startswith("CREATE") or sql_u.startswith("CREATE INDEX"):
            return cur
        if "INSERT INTO PAYMENT_SESSION" in sql_u:
            ref = params[0]
            cols = ("session_key", "link_id", "checkout_url", "amount_cop",
                    "concept", "status", "transaction_id", "provider")
            row = {c: params[i + 1] for i, c in enumerate(cols)}
            row["reference"] = ref
            store[ref] = row
            return cur
        if "WHERE REFERENCE=" in sql_u:
            ref = params[0]
            cur.fetchone = lambda: Row(store[ref]) if ref in store else None
            return cur
        if "WHERE SESSION_KEY=" in sql_u:
            sk = params[0]
            matches = [r for r in store.values() if r.get("session_key") == sk]
            cur.fetchone = lambda: Row(matches[-1]) if matches else None
            return cur
        return cur

    c = MagicMock()
    c.execute = execute
    c.commit = MagicMock()
    return c


def test_generar_link_pago_calls_nest_checkout_only(conn):
    nest = {
        "reference": "SEG-TEST01",
        "checkoutUrl": "https://sandbox.polar.sh/c/x",
        "linkId": "chk_1",
        "provider": "polar",
        "status": "PENDING",
        "amountCop": 50000,
        "concept": "Prima",
        "demo": False,
    }
    with patch("app.payments.requests.post", return_value=_FakeResp(nest)) as post:
        with patch("app.payments.requests.get") as get:
            with patch("app.payments.requests.patch") as patch_req:
                out = payments.generar_link_pago(
                    conn, "t:web:1", "11111111-1111-1111-1111-111111111111",
                    {"monto_cop": 50000, "descripcion": "Prima"})

    assert out["reference"] == "SEG-TEST01"
    assert out["checkout_url"] == "https://sandbox.polar.sh/c/x"
    assert out["demo"] is False
    post.assert_called_once()
    url = post.call_args.args[0]
    assert url.endswith("/api/v1/payments/checkout")
    assert "polar.sh/v1" not in url
    get.assert_not_called()
    patch_req.assert_not_called()
    headers = post.call_args.kwargs["headers"]
    assert headers["X-Tenant-Id"] == "11111111-1111-1111-1111-111111111111"


def test_generar_link_pago_demo_via_nest(conn):
    nest = {
        "reference": "SEG-DEMO01",
        "checkoutUrl": None,
        "linkId": "demo-SEG-DEMO01",
        "provider": "demo",
        "status": "PENDING",
        "amountCop": 10000,
        "concept": "Demo",
        "demo": True,
    }
    with patch("app.payments.requests.post", return_value=_FakeResp(nest)):
        out = payments.generar_link_pago(
            conn, "t:web:2", "11111111-1111-1111-1111-111111111111",
            {"monto_cop": 10000})
    assert out["demo"] is True
    assert out["checkout_url"] is None
    assert "modo demo" in (out.get("nota") or "")


def test_verificar_pago_uses_nest_get_and_demo_patch(conn):
    # Seed local session row
    payments._save(
        conn, "SEG-DEMO02", session_key="t:web:3", link_id="demo-x",
        checkout_url=None, amount_cop=1000, concept="x", status="PENDING",
        provider="demo")

    backend = {
        "reference": "SEG-DEMO02",
        "status": "PENDING",
        "provider": "demo",
        "transactionId": None,
    }
    with patch("app.payments.requests.get",
               return_value=_FakeResp(backend)) as get:
        with patch("app.payments.requests.patch",
                   return_value=_FakeResp({})) as patch_req:
            with patch("app.payments.requests.post") as post:
                out = payments.verificar_pago(
                    conn, "t:web:3", "11111111-1111-1111-1111-111111111111", {})

    assert out["status"] == "APPROVED"
    get.assert_called_once()
    assert "/api/v1/payments/SEG-DEMO02" in get.call_args.args[0]
    patch_req.assert_called_once()
    post.assert_not_called()


def test_payments_module_has_no_polar_token_import():
    import app.payments as mod
    import inspect
    src = inspect.getsource(mod)
    assert "POLAR_ACCESS_TOKEN" not in src or "Nest sin POLAR_ACCESS_TOKEN" in src
    assert "sandbox-api.polar.sh" not in src
    assert "from .config import" in src
    assert "BACKEND_URL" in src
    # No Polar HTTP helpers
    assert "_polar_create_checkout" not in src
    assert "Authorization" not in src or "Bearer" not in src
