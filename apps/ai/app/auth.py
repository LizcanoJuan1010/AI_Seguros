"""Autenticación por JWT (login) + tenencia desde el token — patrón Paloma.

Reutiliza el decode HS256 de Paloma (`features/auth.py`) SIN PyJWT: solo
`hmac`, `hashlib`, `base64`, `json` y `time` de la stdlib. El backend NestJS
firma access tokens HS256 con `JWT_SECRET` cuyos claims son
`{sub, email, name, role, teamId, type:"access", iat, exp}`; aquí verificamos
firma + expiración + `type=="access"` y derivamos `(tenant_id, role)`.

El tenant sale del login (`claims.teamId`), no de un header manual; el rol sale
de `claims.role`. Si no hay token válido se cae al comportamiento previo
(`X-Tenant-Id`/tenant demo y `manager_key`) para compatibilidad servicio-a-servicio.
"""
import hashlib
import hmac
import json
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Optional

from . import config

# ---------------------------------------------------------------------------
# Helpers JWT mínimos (solo HS256 — evita añadir PyJWT como dependencia)
# Copiados del patrón de Paloma: _b64url_decode / _jwt_decode / decode_access_token.
# ---------------------------------------------------------------------------


def _b64url_encode(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return urlsafe_b64decode(s + "=" * padding)


def _jwt_encode(payload: dict, secret: str) -> str:
    """Firma un JWT HS256 (usado en pruebas/verificación; simétrico a _jwt_decode)."""
    header = {"alg": "HS256", "typ": "JWT"}
    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode()),
        _b64url_encode(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = f"{segments[0]}.{segments[1]}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    segments.append(_b64url_encode(signature))
    return ".".join(segments)


def _jwt_decode(token: str, secret: str) -> Optional[dict]:
    """Decodifica y verifica un JWT HS256. Devuelve None ante cualquier fallo."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        signing_input = f"{parts[0]}.{parts[1]}".encode()
        expected_sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(parts[2])
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(parts[1]))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def decode_token(token: str) -> Optional[dict]:
    """Verifica firma (JWT_SECRET) + exp + type=='access'.

    Devuelve los claims `{sub, email, name, role, teamId, ...}` o None si el token
    es inválido, está expirado o no es un access token."""
    if not token:
        return None
    data = _jwt_decode(token, config.JWT_SECRET)
    if data and data.get("type") == "access":
        return data
    return None


# Alias por compatibilidad con la nomenclatura de Paloma / AUTH.md.
decode_access_token = decode_token


# ---------------------------------------------------------------------------
# Resolución de identidad (tenant + rol) desde el JWT del login, con fallback.
# ---------------------------------------------------------------------------

_MANAGER_ROLES = {"GERENTE", "ADMIN"}


def resolve_identity(
    authorization: Optional[str],
    x_tenant_id: Optional[str],
    manager_key: Optional[str],
) -> tuple[str, str]:
    """Deriva `(tenant_id, role)` para el turno.

    - Si hay `Authorization: Bearer <token>` y decodifica válido:
        `tenant_id = claims['teamId']` y
        `role = 'gerente'` si `claims.role in {GERENTE, ADMIN}` else `'cliente'`.
    - Si no hay token válido (fallback, comportamiento previo):
        `tenant_id = x_tenant_id or DEMO_TENANT_ID` y
        `role = 'gerente'` si `manager_key == MANAGER_API_KEY` else `'cliente'`.
    """
    if authorization:
        scheme, _, raw = authorization.partition(" ")
        if scheme.lower() == "bearer":
            claims = decode_token(raw.strip())
            if claims:
                tenant_id = claims.get("teamId") or x_tenant_id or config.DEMO_TENANT_ID
                role = "gerente" if claims.get("role") in _MANAGER_ROLES else "cliente"
                return tenant_id, role

    tenant_id = x_tenant_id or config.DEMO_TENANT_ID
    role = "gerente" if manager_key and manager_key == config.MANAGER_API_KEY else "cliente"
    return tenant_id, role
