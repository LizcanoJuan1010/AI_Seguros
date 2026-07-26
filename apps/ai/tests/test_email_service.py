"""Ruteo de proveedores de correo (`email_service.send_email`).

Lo que importa cubrir: la config REAL de producción (Railway) es Resend-only
— SMTP vacío porque Railway bloquea los puertos SMTP salientes — y hubo un
hueco donde un SMTP a medias en el entorno dejaba a Resend en la sombra: si
SMTP fallaba, el correo se perdía sin intentar Resend. Estos tests fijan el
contrato para que no regrese.

Ningún test toca la red: el SDK de `resend` se sustituye por un doble y el
envío SMTP por un stub. Marcados `unit` (no necesitan Postgres).
"""
import asyncio
import sys
import types

import pytest

from app import email_service as es

pytestmark = pytest.mark.unit


@pytest.fixture
def resend_falso(monkeypatch):
    """Sustituye el SDK de resend por un doble que registra los envíos."""
    llamadas: list[dict] = []

    class _Emails:
        @staticmethod
        def send(params):
            llamadas.append(params)
            return {"id": "email_fake_001"}

    fake = types.ModuleType("resend")
    fake.Emails = _Emails
    fake.api_key = None
    monkeypatch.setitem(sys.modules, "resend", fake)
    # Circuito cerrado y sin throttle pendiente entre tests.
    monkeypatch.setattr(es, "_resend_circuit_open_until", 0.0)
    monkeypatch.setattr(es, "_resend_last_send_ts", 0.0)
    return llamadas


def test_produccion_resend_only_rutea_por_resend(monkeypatch, resend_falso):
    """La config de Railway: solo RESEND_API_KEY (+FROM), SMTP vacío."""
    monkeypatch.setattr(es, "SMTP_USER", "")
    monkeypatch.setattr(es, "SMTP_PASSWORD", "")
    monkeypatch.setattr(es, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(es, "RESEND_FROM_EMAIL", "Tequendama <hola@dominio.co>")

    r = asyncio.run(es.send_email("cliente@ejemplo.com", "Asunto", "<b>x</b>"))

    assert r["status"] == "sent"
    assert len(resend_falso) == 1
    assert resend_falso[0]["from"] == "Tequendama <hola@dominio.co>"
    assert resend_falso[0]["to"] == ["cliente@ejemplo.com"]


def test_smtp_fallido_cae_a_resend(monkeypatch, resend_falso):
    """El hueco original: SMTP configurado pero roto (Railway bloquea los
    puertos) NO debe perder el correo — reintenta por Resend."""
    monkeypatch.setattr(es, "SMTP_USER", "user@gmail.com")
    monkeypatch.setattr(es, "SMTP_PASSWORD", "clave")
    monkeypatch.setattr(es, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(es, "RESEND_FROM_EMAIL", "Tequendama <hola@dominio.co>")

    def smtp_roto(*a, **k):
        raise TimeoutError("Connection timed out")

    monkeypatch.setattr(es, "_smtp_send_sync", smtp_roto)

    r = asyncio.run(es.send_email("cliente@ejemplo.com", "Asunto", "<b>x</b>"))

    assert r["status"] == "sent"
    assert len(resend_falso) == 1


def test_smtp_fallido_sin_resend_reporta_error(monkeypatch, resend_falso):
    """Sin Resend de respaldo, el fallo SMTP se reporta — nunca se finge éxito."""
    monkeypatch.setattr(es, "SMTP_USER", "user@gmail.com")
    monkeypatch.setattr(es, "SMTP_PASSWORD", "clave")
    monkeypatch.setattr(es, "RESEND_API_KEY", "")

    def smtp_roto(*a, **k):
        raise TimeoutError("Connection timed out")

    monkeypatch.setattr(es, "_smtp_send_sync", smtp_roto)

    r = asyncio.run(es.send_email("cliente@ejemplo.com", "Asunto", "<b>x</b>"))

    assert r["status"] == "error"
    assert not resend_falso


def test_dominio_no_verificado_abre_circuito_1h(monkeypatch, resend_falso, caplog):
    """Lección de Paloma: dominio sin verificar → circuito abierto 1 h y los
    envíos siguientes se descartan como skipped SIN llamar al API (por eso en
    producción los correos 'desaparecen' en bloque si el FROM está mal)."""
    monkeypatch.setattr(es, "SMTP_USER", "")
    monkeypatch.setattr(es, "SMTP_PASSWORD", "")
    monkeypatch.setattr(es, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(es, "RESEND_FROM_EMAIL", "Tequendama <hola@sin-verificar.co>")

    class _EmailsRotos:
        @staticmethod
        def send(params):
            raise RuntimeError("The dominio.co domain is not verified")

    sys.modules["resend"].Emails = _EmailsRotos

    r1 = asyncio.run(es.send_email("a@ejemplo.com", "x", "<b>x</b>"))
    assert r1["status"] == "skipped"
    assert r1["reason"] == "domain_not_verified"

    # Segundo envío: ni siquiera llama al API (circuito abierto).
    r2 = asyncio.run(es.send_email("b@ejemplo.com", "x", "<b>x</b>"))
    assert r2["status"] == "skipped"
    assert "circuit_open" in r2["reason"] or "circuit" in r2["reason"]


def test_sin_proveedor_skipped_explicito(monkeypatch, resend_falso):
    monkeypatch.setattr(es, "SMTP_USER", "")
    monkeypatch.setattr(es, "SMTP_PASSWORD", "")
    monkeypatch.setattr(es, "RESEND_API_KEY", "")

    r = asyncio.run(es.send_email("a@ejemplo.com", "x", "<b>x</b>"))

    assert r == {"status": "skipped", "reason": "no_email_provider"}
