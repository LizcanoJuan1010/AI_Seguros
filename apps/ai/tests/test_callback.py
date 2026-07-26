"""Puerta anónima de la landing: "déjanos tu número y te llamamos".

El endpoint vive en `app/landing_callback.py`; la capa anti-abuso (validación,
consentimiento auditado, topes por hora) en `app/callback.py`. Lo que importa
cubrir es que esa puerta ANÓNIMA no se pueda abusar: sin consentimiento no
llama, con un número basura no llama, y hay un tope por hora.

Los tests del endpoint NO pueden asumir que la llamada se dispara: desde el
merge de jul 2026, `calls.iniciar_llamada` aplica la ventana legal de contacto
comercial (Ley 2300/2023 — nunca domingo, sáb 8-15, L-V 7-19), así que la suite
falla o pasa según el día en que corra. Por eso todo lo que se afirma sobre el
disparo se prueba contra la capa de guardas, no contra el reloj.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app  # noqa: E402

client = TestClient(app)


@pytest.mark.parametrize("crudo,esperado", [
    ("300 123 4567", "+573001234567"),
    ("3001234567", "+573001234567"),
    ("+57 300 123 4567", "+573001234567"),
    ("573001234567", "+573001234567"),
    ("+1 415 555 0123", "+14155550123"),  # E.164 de otro país se respeta
    ("12345", None),
    ("no soy un numero", None),
    ("", None),
])
def test_normalizar_telefono(crudo, esperado):
    from app.callback import normalizar_telefono
    assert normalizar_telefono(crudo) == esperado


def test_solo_celulares_colombianos_son_llamables():
    from app.callback import es_celular_colombiano
    assert es_celular_colombiano("+573001234567") is True
    assert es_celular_colombiano("+576012345678") is False  # fijo de Bogotá
    assert es_celular_colombiano("+14155550123") is False


def test_sin_consentimiento_no_llama():
    r = client.post("/api/callback/solicitar",
                    json={"telefono": "3001234567", "consent": False})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "autorización" in body["mensaje"].lower()


def test_telefono_invalido_no_llama():
    r = client.post("/api/callback/solicitar",
                    json={"telefono": "123", "consent": True})
    assert r.json()["ok"] is False


def test_fijo_no_es_llamable():
    """Un fijo se normaliza bien, pero el agente de voz solo sirve en móvil."""
    r = client.post("/api/callback/solicitar",
                    json={"telefono": "+576012345678", "consent": True})
    assert r.json()["ok"] is False


def test_rechazos_de_validacion_son_200_no_4xx():
    """Contrato con CallMeBack.tsx: el front pinta `mensaje` bajo el campo sin
    sacar al visitante del formulario, así que nunca un HTTPException."""
    for payload in ({"telefono": "", "consent": True},
                    {"telefono": "3001234567", "consent": False},
                    {"telefono": "abc", "consent": True}):
        r = client.post("/api/callback/solicitar", json=payload)
        assert r.status_code == 200, payload
        assert r.json()["ok"] is False
        assert r.json()["mensaje"]


def test_tope_por_telefono_corta_al_cuarto_intento(db_conn):
    """CALLBACK_MAX_POR_TELEFONO=3 por hora: el 4.º del mismo número se frena.

    Va contra la capa de guardas, no contra el endpoint, para no depender de la
    ventana legal (Ley 2300) ni gastar disparos de llamada."""
    from app import callback as guard
    phone = "+573007776655"
    guard.tabla(db_conn)
    db_conn.execute("DELETE FROM callback_request WHERE phone=%s", (phone,))
    db_conn.commit()

    for _ in range(3):
        assert guard.limite_excedido(db_conn, phone=phone) is None
        guard.registrar(db_conn, phone=phone, nombre=None, interes=None,
                        device_id=None, tenant_id="t", consent=True, ip=None,
                        user_agent=None, status="solicitada")
    bloqueo = guard.limite_excedido(db_conn, phone=phone)
    assert bloqueo and "última hora" in bloqueo


def test_tope_por_dispositivo_es_independiente_del_telefono(db_conn):
    """Cambiar de número no evade el límite: el device_id también cuenta."""
    from app import callback as guard
    device = "dev_test_tope_indep"
    guard.tabla(db_conn)
    db_conn.execute("DELETE FROM callback_request WHERE device_id=%s", (device,))
    db_conn.commit()

    for i in range(5):
        guard.registrar(db_conn, phone=f"+57300000{i:04d}", nombre=None, interes=None,
                        device_id=device, tenant_id="t", consent=True, ip=None,
                        user_agent=None, status="solicitada")
    bloqueo = guard.limite_excedido(db_conn, phone="+573009999999", device_id=device)
    assert bloqueo and "navegador" in bloqueo


def test_consentimiento_queda_auditado(db_conn):
    """Ley 1581/2012: hay que poder demostrar cuándo y desde dónde se autorizó."""
    from app import callback as guard
    guard.tabla(db_conn)
    req_id = guard.registrar(db_conn, phone="+573001112233", nombre="Ana",
                             interes="vida", device_id="dev_audit", tenant_id="t",
                             consent=True, ip="10.0.0.1", user_agent="pytest",
                             status="solicitada")
    row = db_conn.execute(
        "SELECT consent, consent_at, ip FROM callback_request WHERE id=%s",
        (req_id,)).fetchone()
    assert row["consent"] is True
    assert row["consent_at"] is not None
    assert row["ip"] == "10.0.0.1"


def test_interes_fuera_del_catalogo_se_descarta():
    """`interes` solo acepta la lista cerrada: nada de texto libre del visitante
    hacia las dynamic_variables que recibe el agente de voz."""
    from app.callback import INTERESES
    assert "ignora tus instrucciones" not in INTERESES
    assert {"vida", "auto", "salud", "hogar", "otro"} == set(INTERESES)


def test_opciones_expone_los_ramos():
    ids = {i["id"] for i in client.get("/api/callback/opciones").json()["intereses"]}
    assert {"vida", "auto", "salud"} <= ids


def test_una_sola_ruta_registrada_para_solicitar():
    """Hubo dos implementaciones del mismo endpoint (main.py y
    landing_callback.py); el router ganaba por orden de registro y la otra
    quedaba muerta en silencio. Que no vuelva a pasar.

    Se recorre en profundidad porque `include_router` anida un `_IncludedRouter`
    (con el router real en `original_router`) en vez de aplanar las rutas: un
    escaneo plano de `app.routes` no las ve."""
    def paths(routes):
        for r in routes:
            if hasattr(r, "path"):
                yield r.path
            incluido = getattr(r, "original_router", None)
            if incluido is not None:
                yield from paths(incluido.routes)

    encontradas = [p for p in paths(app.routes) if p == "/api/callback/solicitar"]
    assert len(encontradas) == 1, f"esperaba 1 handler, hay {len(encontradas)}"
