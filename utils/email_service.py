"""
Sistema de Email Automatico para AndroTech.

Enviamos los emails usando `email.message.EmailMessage` + `smtplib`
directamente, en lugar de Flask-Mail, porque Flask-Mail 0.10 presenta un bug
conocido de codificacion: aunque le pases `charset='utf-8'` al Message, las
cabeceras (Subject, From, To) y el cuerpo HTML con caracteres no ASCII
(acentos, em dash, emojis) disparan UnicodeEncodeError del codec 'ascii'.

La API nativa de Python 3.6+ maneja Unicode correctamente via el modulo `email`,
codificando Subject con Base64/Quoted-Printable y el cuerpo con el charset
declarado. Mantenemos la interfaz publica identica (los mismos metodos que
consume app.py) para no tocar nada fuera de este fichero.
"""

import smtplib
import logging
from email.message import EmailMessage
from datetime import datetime
from flask import current_app, render_template

logger = logging.getLogger(__name__)


class EmailService:
    """Servicio de email para notificaciones automaticas (SMTP directo)."""

    def __init__(self, _legacy_mail_instance=None):
        # El parametro se conserva por compatibilidad con la firma original
        # (app.py llama a EmailService(mail)). No se usa: leemos la config
        # directamente de current_app.config en cada envio.
        self._unused = _legacy_mail_instance

    # ──────────────────────────────────────────────────────────────────────
    # Core: envio de bajo nivel con SMTP nativo y encoding correcto
    # ──────────────────────────────────────────────────────────────────────
    def _send(self, *, subject: str, to_email: str, html_body: str,
              attachments: list[tuple] | None = None) -> None:
        """Envia un email HTML (con adjuntos opcionales) via SMTP.

        `attachments` es una lista de tuplas (filename, mime_type, data_bytes).
        Lanza la excepcion al llamador para que decida como manejarla.
        """
        cfg = current_app.config
        host    = cfg.get('MAIL_SERVER', 'smtp.gmail.com')
        port    = int(cfg.get('MAIL_PORT', 587))
        use_tls = bool(cfg.get('MAIL_USE_TLS', True))
        use_ssl = bool(cfg.get('MAIL_USE_SSL', False))
        user    = cfg.get('MAIL_USERNAME', '') or ''
        pwd     = cfg.get('MAIL_PASSWORD', '') or ''
        sender  = cfg.get('MAIL_DEFAULT_SENDER') or user

        if not user or not pwd:
            raise RuntimeError(
                'SMTP no configurado: faltan MAIL_USERNAME o MAIL_PASSWORD en .env'
            )

        # EmailMessage codifica Subject/From/To correctamente con MIME RFC 2047
        # cuando contienen caracteres no-ASCII (acentos, em dash, emojis).
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From']    = sender
        msg['To']      = to_email
        # Cuerpo HTML con charset explicito: la policy por defecto codifica en
        # quoted-printable y declara `Content-Type: text/html; charset="utf-8"`.
        msg.set_content(
            'Este email requiere un cliente compatible con HTML para verse correctamente.',
            subtype='plain', charset='utf-8',
        )
        msg.add_alternative(html_body, subtype='html', charset='utf-8')

        # Adjuntos (ej. factura PDF)
        if attachments:
            for filename, mime_type, data in attachments:
                maintype, _, subtype = (mime_type or 'application/octet-stream').partition('/')
                msg.add_attachment(
                    data, maintype=maintype, subtype=subtype or 'octet-stream',
                    filename=filename,
                )

        # Conexion SMTP (el timeout global lo fija socket.setdefaulttimeout(20)
        # en app.py, por lo que no hace falta pasarlo aqui).
        if use_ssl:
            smtp = smtplib.SMTP_SSL(host, port)
        else:
            smtp = smtplib.SMTP(host, port)

        try:
            smtp.ehlo()
            if use_tls and not use_ssl:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(user, pwd)
            smtp.send_message(msg)
        finally:
            try:
                smtp.quit()
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────────────
    # API publica (misma firma que antes para no romper app.py)
    # ──────────────────────────────────────────────────────────────────────
    def send_payment_confirmation(self, to_email, cliente_nombre, reparacion_id,
                                  precio, descripcion, pdf_data=None):
        """Confirmacion de pago, opcionalmente con factura PDF adjunta."""
        try:
            html = render_template(
                'emails/payment_confirmation.html',
                cliente_nombre=cliente_nombre,
                reparacion_id=reparacion_id,
                precio=precio,
                descripcion=descripcion,
                fecha_pago=datetime.now().strftime('%d/%m/%Y %H:%M'),
                year=datetime.now().year,
            )
            attachments = None
            if pdf_data is not None:
                pdf_bytes = pdf_data.read() if hasattr(pdf_data, 'read') else pdf_data
                attachments = [(f'factura_reparacion_{reparacion_id}.pdf',
                                'application/pdf', pdf_bytes)]
                logger.debug(f'PDF adjuntado al email de reparacion {reparacion_id}')

            self._send(
                subject=f'Confirmacion de Pago - Reparacion #{reparacion_id} - AndroTech',
                to_email=to_email, html_body=html, attachments=attachments,
            )
            logger.info(f'Email de confirmacion de pago enviado a {to_email} para reparacion {reparacion_id}')
        except Exception as e:
            logger.error(f'Error enviando email de confirmacion de pago: {type(e).__name__}: {str(e)}')
            raise

    def send_repair_status_update(self, to_email, cliente_nombre, reparacion_id,
                                  estado_anterior, estado_nuevo, dispositivo, descripcion):
        """Actualizacion de estado de una reparacion."""
        try:
            html = render_template(
                'emails/repair_status_update.html',
                cliente_nombre=cliente_nombre,
                reparacion_id=reparacion_id,
                estado_anterior=estado_anterior,
                estado_nuevo=estado_nuevo,
                dispositivo=dispositivo,
                descripcion=descripcion,
                fecha_actualizacion=datetime.now().strftime('%d/%m/%Y %H:%M'),
                year=datetime.now().year,
            )
            self._send(
                subject=f'Actualizacion de Estado - Reparacion #{reparacion_id} - AndroTech',
                to_email=to_email, html_body=html,
            )
            logger.info(f'Email de actualizacion de estado enviado a {to_email} para reparacion {reparacion_id}: {estado_anterior} -> {estado_nuevo}')
        except Exception as e:
            logger.error(f'Error enviando email de actualizacion de estado: {str(e)}')
            raise

    def send_invoice(self, to_email, cliente_nombre, reparacion_id, precio,
                     descripcion, fecha_factura=None):
        """Factura (usa la misma plantilla que confirmacion de pago)."""
        try:
            html = render_template(
                'emails/payment_confirmation.html',
                cliente_nombre=cliente_nombre,
                reparacion_id=reparacion_id,
                precio=precio,
                descripcion=descripcion,
                fecha_pago=fecha_factura or datetime.now().strftime('%d/%m/%Y'),
                year=datetime.now().year,
            )
            self._send(
                subject=f'Factura - Reparacion #{reparacion_id} - AndroTech',
                to_email=to_email, html_body=html,
            )
            logger.info(f'Email de factura enviado a {to_email} para reparacion {reparacion_id}')
        except Exception as e:
            logger.error(f'Error enviando email de factura: {str(e)}')
            raise

    def send_nueva_reparacion(self, to_email, cliente_nombre, reparacion_id,
                              dispositivo, descripcion, fecha_entrada):
        """Notificacion de nueva reparacion registrada."""
        try:
            html = render_template(
                'emails/nueva_reparacion.html',
                cliente_nombre=cliente_nombre,
                reparacion_id=reparacion_id,
                dispositivo=dispositivo,
                descripcion=descripcion,
                fecha_entrada=fecha_entrada,
                year=datetime.now().year,
            )
            self._send(
                subject=f'Nueva Reparacion Registrada #{reparacion_id} - AndroTech',
                to_email=to_email, html_body=html,
            )
            logger.info(f'Email de nueva reparacion enviado a {to_email} para reparacion {reparacion_id}')
        except Exception as e:
            logger.error(f'Error enviando email de nueva reparacion: {type(e).__name__}: {str(e)}')
            raise

    def send_bienvenida_cliente(self, to_email, cliente_nombre):
        """Email de bienvenida a un nuevo cliente."""
        try:
            html = render_template(
                'emails/bienvenida_cliente.html',
                cliente_nombre=cliente_nombre,
                year=datetime.now().year,
            )
            self._send(
                subject='Bienvenido a AndroTech - Servicio Tecnico Especializado',
                to_email=to_email, html_body=html,
            )
            logger.info(f'Email de bienvenida enviado a {to_email} para cliente {cliente_nombre}')
        except Exception as e:
            logger.error(f'Error enviando email de bienvenida: {type(e).__name__}: {str(e)}')
            raise

    def send_test(self, to_email: str, cliente_nombre: str = 'Administrador') -> None:
        """Email de prueba (usa la plantilla de bienvenida). Usado por /admin/test-email."""
        html = render_template(
            'emails/bienvenida_cliente.html',
            cliente_nombre=cliente_nombre,
            year=datetime.now().year,
        )
        self._send(
            subject='AndroTech - Prueba de envio de email',
            to_email=to_email, html_body=html,
        )
