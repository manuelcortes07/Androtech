"""Capa de notificaciones abstracta (B6) — COSTURA, no integración.

Una única interfaz `Notificador.enviar(canal, ...)` que HOY implementa el canal
`email` (sobre el `EmailService` ya existente) y deja registrado el enchufe para
canales futuros (SMS, WhatsApp, push…) SIN integrar ningún proveedor ni pedir
cuentas. Añadir un canal mañana = `registrar_canal('sms', fn)`, no reescribir
los puntos de envío.

Patrón: los handlers no llaman directamente a EmailService; llaman a
`notificador.enviar('email', destinatario, asunto, html)`. Cuando exista SMS,
el mismo punto de llamada podrá enrutar por preferencia del taller (ver
`settings.py`) sin tocar la lógica de negocio.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("androtech")


class CanalNoDisponible(Exception):
    """Se solicitó un canal de notificación que no está registrado."""


class Notificador:
    def __init__(self, email_service=None):
        self._email_service = email_service
        self._backends = {}
        if email_service is not None:
            self._backends["email"] = self._enviar_email

    def registrar_canal(self, canal: str, fn) -> None:
        """Enchufe para canales futuros. `fn(destinatario, asunto, cuerpo, **kw)`
        debe devolver algo veraz si el envío tuvo éxito."""
        self._backends[canal] = fn

    def canales(self) -> list[str]:
        return sorted(self._backends.keys())

    def enviar(self, canal: str, destinatario: str, asunto: str,
               cuerpo_html: str, **kwargs) -> bool:
        """Envía por `canal`. Lanza CanalNoDisponible si no está registrado.
        Cualquier fallo del backend se captura y se devuelve False (un envío
        que falla nunca debe tumbar el flujo de negocio)."""
        backend = self._backends.get(canal)
        if backend is None:
            raise CanalNoDisponible(
                f"Canal de notificación '{canal}' no disponible. "
                f"Registrados: {self.canales()}"
            )
        try:
            return bool(backend(destinatario, asunto, cuerpo_html, **kwargs))
        except Exception as e:  # pragma: no cover (defensivo)
            logger.warning(
                '{"event": "notificacion_fallo", "canal": "%s", "error": %r}'
                % (canal, str(e))
            )
            return False

    # ── Backend de email (sobre el EmailService existente) ──────────────────
    def _enviar_email(self, destinatario: str, asunto: str, cuerpo_html: str,
                      **kwargs) -> bool:
        if self._email_service is None:
            return False
        self._email_service._send(subject=asunto, to_email=destinatario,
                                  html_body=cuerpo_html)
        return True
