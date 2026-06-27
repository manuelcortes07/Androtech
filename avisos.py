"""Avisos automáticos al cliente final por email (notificaciones de estado).

Punto ÚNICO que decide SI y CÓMO se avisa al cliente cuando cambia el estado de
su reparación. Cuatro guardas — TODAS deben pasar para que salga el email:

  1. el estado realmente cambió,
  2. el cliente tiene email,
  3. el cliente NO se ha dado de baja (`Cliente.acepta_emails`, B3),
  4. el taller tiene activas las notificaciones automáticas (`TallerSetting`, B4).

El envío es un EFECTO SECUNDARIO del cambio de estado: cualquier fallo (SMTP
caído, plantilla, etc.) se captura y se loguea, pero NUNCA propaga — el taller
guarda su reparación aunque el correo no salga. White-label: el `Notificador`
usa el branding del taller dueño (`EmailService._emisor()`), que se resuelve por
`g.taller_id`/`request` de la petición en curso.
"""

from __future__ import annotations

import logging

from flask import g, url_for

from services import notificador
from settings import get_setting
from tokens import generar_token_baja

logger = logging.getLogger("androtech")

# Clave de TallerSetting que enciende/apaga los avisos automáticos (B4). Default
# "1" (activados) si el taller nunca lo tocó.
SETTING_AVISOS = "notif_cambio_estado"


def taller_avisos_activos() -> bool:
    """¿El taller activo tiene los avisos automáticos encendidos? (default sí)."""
    return get_setting(SETTING_AVISOS, "1") != "0"


def _url_seguimiento(codigo_publico) -> str | None:
    """URL absoluta al portal de seguimiento por código (consulta?codigo=…)."""
    if not codigo_publico:
        return None
    try:
        return url_for("publico.consulta", codigo=codigo_publico, _external=True)
    except Exception:
        return None


def _url_baja(cliente_id) -> str | None:
    """URL absoluta de baja firmada para ESTE cliente del taller activo."""
    if not cliente_id:
        return None
    try:
        token = generar_token_baja(cliente_id, g.taller_id)
        return url_for("publico.baja_notificaciones", token=token, _external=True)
    except Exception:
        return None


def avisar_presupuesto_enviado(*, reparacion_id, cliente_email, cliente_nombre,
                               dispositivo, precio, caduca_en,
                               codigo_publico=None) -> str:
    """Email al cliente cuando el taller le ENVÍA un presupuesto para aprobar.

    TRANSACCIONAL y DELIBERADO (el taller pulsa "enviar"): NO se sujeta al opt-out
    de avisos automáticos ni al interruptor del taller — el cliente necesita el
    presupuesto para poder responder. Sólo exige un email válido. Best-effort:
    'enviado' | 'sin_email' | 'error' (nunca lanza)."""
    if not cliente_email:
        logger.info('{"event": "presupuesto_email_omitido", "motivo": "sin_email", '
                    '"reparacion_id": "%s"}' % reparacion_id)
        return "sin_email"
    try:
        notificador.enviar_email(
            "send_presupuesto_enviado",
            to_email=cliente_email,
            cliente_nombre=cliente_nombre,
            reparacion_id=reparacion_id,
            dispositivo=dispositivo,
            precio=precio,
            caduca_en=caduca_en,
            tracking_url=_url_seguimiento(codigo_publico),
        )
        logger.info('{"event": "presupuesto_email_enviado", "reparacion_id": "%s"}'
                    % reparacion_id)
        return "enviado"
    except Exception:
        logger.exception(
            "Error enviando email de presupuesto para reparacion %s" % reparacion_id
        )
        return "error"


def avisar_cambio_estado(*, reparacion_id, cliente_email, cliente_nombre,
                         estado_anterior, estado_nuevo, dispositivo, descripcion,
                         cliente_id=None, codigo_publico=None,
                         acepta_emails: bool = True) -> str:
    """Envía (o no) el aviso de cambio de estado al cliente final.

    Devuelve un motivo (para log/test), nunca lanza:
      'enviado' | 'sin_cambio' | 'sin_email' | 'baja' | 'taller_off' | 'error'.
    """
    if estado_anterior == estado_nuevo:
        return "sin_cambio"
    if not cliente_email:
        logger.info('{"event": "aviso_estado_omitido", "motivo": "sin_email", '
                    '"reparacion_id": "%s"}' % reparacion_id)
        return "sin_email"
    if not acepta_emails:
        logger.info('{"event": "aviso_estado_omitido", "motivo": "cliente_baja", '
                    '"reparacion_id": "%s"}' % reparacion_id)
        return "baja"
    if not taller_avisos_activos():
        logger.info('{"event": "aviso_estado_omitido", "motivo": "taller_off", '
                    '"reparacion_id": "%s"}' % reparacion_id)
        return "taller_off"

    try:
        notificador.enviar_email(
            "send_repair_status_update",
            to_email=cliente_email,
            cliente_nombre=cliente_nombre,
            reparacion_id=reparacion_id,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_nuevo,
            dispositivo=dispositivo,
            descripcion=descripcion,
            tracking_url=_url_seguimiento(codigo_publico),
            baja_url=_url_baja(cliente_id),
        )
        logger.info('{"event": "aviso_estado_enviado", "reparacion_id": "%s", '
                    '"estado": "%s"}' % (reparacion_id, estado_nuevo))
        return "enviado"
    except Exception:
        logger.exception(
            "Error enviando aviso de cambio de estado para reparacion %s" % reparacion_id
        )
        return "error"
