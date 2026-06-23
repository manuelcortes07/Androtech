"""Servicios compartidos sin estado de app (refactor B1 — blueprints).

`email_service` y `notificador` no necesitan la app para construirse
(`EmailService` lee `current_app.config` en cada envío). Se definen aquí para que
los blueprints los importen sin ciclar con `app.py`.

⚠️ Mantener una ÚNICA instancia: los tests parchean `app.email_service._send`
y `app.notificador.enviar_email`; `app.py` re-exporta estas mismas instancias.
"""

from __future__ import annotations

from notifications import Notificador
from utils.email_service import EmailService

email_service = EmailService()
notificador = Notificador(email_service)
