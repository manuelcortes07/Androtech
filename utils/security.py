"""Security-related helpers and validators.

This module currently handles CSRF token generation/validation and some
basic input validators used in various routes.  Moving them here helps
keep the application file focused on routing and orchestration.
"""

import hmac
import secrets
from functools import wraps

from flask import flash, redirect, request, session


def ensure_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(16)


def inject_csrf_token():
    return dict(csrf_token=session.get('csrf_token'))


def validate_csrf():
    """Valida el token CSRF de la petición POST.

    Acepta el token por el campo de formulario `csrf_token` o por la cabecera
    `X-CSRFToken` (peticiones JSON, p. ej. la firma). Comparación en tiempo
    constante con hmac.compare_digest (hallazgo H11).
    """
    sent = request.form.get('csrf_token', '') or request.headers.get('X-CSRFToken', '')
    expected = session.get('csrf_token', '')
    if not sent or not expected or not hmac.compare_digest(str(sent), str(expected)):
        flash('Formulario inválido o expirado. Intenta de nuevo.', 'danger')
        return False
    return True


def csrf_protect(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            if not validate_csrf():
                return redirect(request.url)
        return f(*args, **kwargs)
    return decorated_function


def validar_contraseña(contraseña):
    """Validate password strength.

    Returns (bool, str) — True and empty string if valid,
    False and an error message otherwise.

    Rules:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    """
    if len(contraseña) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres."
    if not any(c.isupper() for c in contraseña):
        return False, "La contraseña debe contener al menos una mayúscula."
    if not any(c.islower() for c in contraseña):
        return False, "La contraseña debe contener al menos una minúscula."
    if not any(c.isdigit() for c in contraseña):
        return False, "La contraseña debe contener al menos un número."
    return True, ""


def validar_precio(precio):
    """Return ``True`` if ``precio`` can be cast to a positive float.

    Used by route handlers to enforce business rules: non-admins should
    not be able to save zero or negative amounts.
    """
    try:
        p = float(precio)
        return p > 0
    except Exception:
        return False
