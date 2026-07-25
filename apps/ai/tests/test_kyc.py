"""Pruebas del cierre KYC: documentos, verificación de identidad y gate de emisión.

La biometría real (YuNet + SFace) se valida aparte; aquí el veredicto se controla
(monkeypatch) para probar de forma determinista la persistencia y, sobre todo, que
`emitir_poliza` NO cierra la venta hasta tener documentos + identidad + datos.

Un test opcional (`SEGURIA_TEST_FACE_DIR` con cedula.jpg/selfie.jpg/otra.jpg) ejerce
el motor biométrico real; sin esa carpeta se salta.
"""
import io
import os

import pytest

from app import identity, intake
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
SVC = {"X-Service-Key": "test-svc"}


def _upload(phone: str, tipo: str, name: str = "doc.jpg") -> str:
    """Sube un archivo dummy como documento KYC y devuelve su file_id.

    El teléfono se pasa URL-encoded; el endpoint normaliza el `+` de todos modos."""
    from urllib.parse import quote
    r = client.post(f"/api/assistant/upload?phone={quote(phone)}&tipo={tipo}",
                    files={"file": (name, io.BytesIO(b"fake-image-bytes"), "image/jpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["documento_kyc_registrado"] == tipo
    return body["file_id"]


def _fill_required_vida() -> dict:
    """Valores dummy para TODOS los campos obligatorios de vida (según el catálogo)."""
    campos = {}
    for f in intake.faltantes("vida", {}):
        t = f.get("tipo")
        if t == "bool":
            campos[f["id"]] = True
        elif t == "number":
            campos[f["id"]] = 1
        elif t == "list":
            campos[f["id"]] = [{"nombre": "Beneficiario 1", "parentesco": "hijo", "porcentaje": 100}]
        elif t == "select":
            opts = f.get("opciones") or ["Simulado"]
            campos[f["id"]] = opts[0]
        else:
            campos[f["id"]] = "N/A"
    return campos


def test_emit_blocked_without_kyc():
    """Con datos + consentimiento pero SIN documentos ni identidad, emitir NO cierra:
    el gate exige completar KYC (documentos + biometría)."""
    phone = "+573001110001"
    client.post("/api/datos-cliente", headers=SVC,
                json={"phone": phone, "full_name": "Ana Torres", "document_id": "1032456789"})
    client.post("/api/consentimiento", headers=SVC, json={"phone": phone, "acepta": True})
    r = client.post("/api/emitir", headers=SVC,
                    json={"phone": phone, "insurance_type": "VIDA", "monthly_premium_cop": 45000})
    assert r.status_code == 200
    body = r.json()
    assert body.get("necesita") == "completar_kyc", body
    assert body.get("identidad_ok") is False
    assert body.get("documentos_ok") is False
    assert "faltan_kyc" in body


def test_identidad_rechazada_bloquea(monkeypatch):
    """Si la biometría rechaza (rostro no coincide), la identidad no queda verificada."""
    phone = "+573001110002"
    monkeypatch.setattr(identity, "verify", lambda d, s, **k: {
        "available": True, "decision": identity.DECISION_RECHAZADO, "score": 0.10,
        "threshold": 0.363, "method": "yunet_sface", "reasons": ["no coincide"]})
    # registra cédula y selfie (dummy), luego verifica
    _upload(phone, "cedula_frente")
    _upload(phone, "selfie")
    v = client.post("/api/identidad/verificar", headers=SVC, json={"phone": phone}).json()
    assert v["decision"] == "rechazado"
    estado = client.get(f"/api/kyc/estado/{phone}?insurance_type=vida", headers=SVC).json()
    assert estado["identidad"]["verificada"] is False


def test_kyc_flow_abre_el_gate(monkeypatch):
    """Con documentos + identidad aprobada + datos + consentimiento, el gate KYC abre."""
    phone = "+573001110003"
    monkeypatch.setattr(identity, "verify", lambda d, s, **k: {
        "available": True, "decision": identity.DECISION_APROBADO, "score": 0.74,
        "threshold": 0.363, "method": "yunet_sface", "doc_face_score": 0.9,
        "selfie_face_score": 0.9, "reasons": ["coincide"]})

    _upload(phone, "cedula_frente")
    _upload(phone, "selfie")
    _upload(phone, "autorizacion_firmada", name="firma.pdf")

    v = client.post("/api/identidad/verificar", headers=SVC, json={"phone": phone}).json()
    assert v["decision"] == "aprobado"

    # datos obligatorios completos (identificación + SARLAFT + salud + beneficiarios...)
    from urllib.parse import quote
    client.post("/api/datos-cliente", headers=SVC, json={
        "phone": phone, "full_name": "Ana Torres", "document_id": "1032456789",
        "birth_date": "1990-05-12", "email": "ana@mail.com", "city": "Bogotá",
        "campos": _fill_required_vida()})
    client.post("/api/consentimiento", headers=SVC, json={"phone": phone, "acepta": True})

    estado = client.get(f"/api/kyc/estado/{quote(phone)}?insurance_type=vida", headers=SVC).json()
    assert estado["identidad"]["verificada"] is True
    assert estado["documentos_faltantes"] == []
    assert estado["listo_para_emitir"] is True, estado["faltantes"]

    # emitir ya NO se bloquea por KYC (puede emitir o pasar a underwriting, pero no
    # devuelve el bloqueo de cumplimiento)
    r = client.post("/api/emitir", headers=SVC, json={
        "phone": phone, "insurance_type": "VIDA", "monthly_premium_cop": 45000})
    body = r.json()
    assert body.get("necesita") != "completar_kyc", body
    assert "faltan_kyc" not in body, body


@pytest.mark.skipif(not os.getenv("SEGURIA_TEST_FACE_DIR"),
                    reason="define SEGURIA_TEST_FACE_DIR con cedula.jpg/selfie.jpg/otra.jpg "
                           "para ejercer el motor biométrico real (YuNet + SFace)")
def test_identity_engine_real():
    """Motor real: misma persona aprueba, distinta rechaza (si hay modelos + fotos)."""
    d = os.environ["SEGURIA_TEST_FACE_DIR"]
    if not identity.available():
        pytest.skip("modelos faciales no disponibles")
    same = identity.verify(f"{d}/cedula.jpg", f"{d}/selfie.jpg")
    assert same["decision"] == identity.DECISION_APROBADO, same
    other = identity.verify(f"{d}/cedula.jpg", f"{d}/otra.jpg")
    assert other["decision"] == identity.DECISION_RECHAZADO, other
