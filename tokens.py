"""Tokens firmados y caducos (B3) con itsdangerous — sin dependencias nuevas.

Se firman con la SECRET_KEY de la app (`current_app.secret_key`). Dos usos:

- Reset de contraseña (1 h): el payload incluye una HUELLA de la contraseña
  actual; en cuanto la contraseña cambia, los enlaces viejos dejan de validar
  (single-use de facto, sin estado en BD).
- Verificación de email (24 h): el payload incluye una huella del email; si el
  email cambia, los enlaces viejos mueren.

Las huellas son `sha256(...)[:16]` — NO exponen ni el hash ni el email (el token
de itsdangerous va firmado pero NO cifrado: su contenido es legible en base64).
"""

from __future__ import annotations

import hashlib

from flask import current_app
from itsdangerous import URLSafeTimedSerializer

_SALT_RESET = "androtech-password-reset"
_SALT_VERIFY = "androtech-email-verify"

MAX_AGE_RESET = 3600        # 1 hora
MAX_AGE_VERIFY = 86400      # 24 horas


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt=salt)


def _fingerprint(valor: str) -> str:
    return hashlib.sha256((valor or "").encode("utf-8")).hexdigest()[:16]


# ─── Reset de contraseña ────────────────────────────────────────────────────
def generar_token_reset(usuario) -> str:
    """Token de reset atado a (usuario, taller) y a la contraseña ACTUAL."""
    return _serializer(_SALT_RESET).dumps({
        "uid": usuario.id,
        "tid": usuario.taller_id,
        "fp": _fingerprint(usuario.password),
    })


def cargar_token_reset(token: str, max_age: int = MAX_AGE_RESET) -> dict:
    """Devuelve {uid, tid, fp}; lanza BadSignature/SignatureExpired si no vale."""
    return _serializer(_SALT_RESET).loads(token, max_age=max_age)


def huella_password(password_hash: str) -> str:
    """Huella de un hash de contraseña, para comparar con la del token."""
    return _fingerprint(password_hash)


# ─── Verificación de email ──────────────────────────────────────────────────
def generar_token_verificacion(taller_id: int, email: str) -> str:
    """Token de verificación atado a (taller, email actual)."""
    return _serializer(_SALT_VERIFY).dumps({
        "tid": taller_id,
        "fp": _fingerprint((email or "").lower()),
    })


def cargar_token_verificacion(token: str, max_age: int = MAX_AGE_VERIFY) -> dict:
    """Devuelve {tid, fp}; lanza BadSignature/SignatureExpired si no vale."""
    return _serializer(_SALT_VERIFY).loads(token, max_age=max_age)


def huella_email(email: str) -> str:
    return _fingerprint((email or "").lower())
