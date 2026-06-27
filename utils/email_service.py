"""
Sistema de Email Automatico (Kintsu).

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

import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage

from flask import current_app, render_template

logger = logging.getLogger(__name__)


class EmailService:
    """Servicio de email para notificaciones automaticas (SMTP directo)."""

    def __init__(self, _legacy_mail_instance=None):
        # El parametro se conserva por compatibilidad con la firma original
        # (app.py llama a EmailService(mail)). No se usa: leemos la config
        # directamente de current_app.config en cada envio.
        self._unused = _legacy_mail_instance

    def _emisor(self) -> dict:
        """Datos del TALLER activo para los emails AL CLIENTE (no la plataforma).

        Añade `logo_url` ABSOLUTA (los clientes de correo no resuelven rutas
        relativas). Se construye con el host de la petición si la hay, o con
        APP_BASE_URL si el email sale en segundo plano (webhook). Si no se puede
        construir una URL absoluta, queda "" y la plantilla degrada al nombre.
        Degrada a un dict con nombre genérico si no hay taller en contexto.
        """
        try:
            from branding import logo_url_absoluto, taller_branding
            m = dict(taller_branding())
            base = None
            try:
                from flask import has_request_context, request
                if has_request_context():
                    base = request.host_url
            except Exception:
                base = None
            m["logo_url"] = logo_url_absoluto(m, base_url=base)
            return m
        except Exception:
            return {"nombre": "Tu taller", "logo_url": ""}

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
            emisor = self._emisor()
            html = render_template(
                'emails/payment_confirmation.html',
                cliente_nombre=cliente_nombre,
                reparacion_id=reparacion_id,
                precio=precio,
                descripcion=descripcion,
                fecha_pago=datetime.now().strftime('%d/%m/%Y %H:%M'),
                year=datetime.now().year,
                emisor=emisor,
            )
            attachments = None
            if pdf_data is not None:
                pdf_bytes = pdf_data.read() if hasattr(pdf_data, 'read') else pdf_data
                attachments = [(f'factura_reparacion_{reparacion_id}.pdf',
                                'application/pdf', pdf_bytes)]
                logger.debug(f'PDF adjuntado al email de reparacion {reparacion_id}')

            self._send(
                subject=f'Confirmacion de Pago - Reparacion #{reparacion_id} - {emisor.get("nombre") or "Tu taller"}',
                to_email=to_email, html_body=html, attachments=attachments,
            )
            logger.info(f'Email de confirmacion de pago enviado a {to_email} para reparacion {reparacion_id}')
        except Exception as e:
            logger.error(f'Error enviando email de confirmacion de pago: {type(e).__name__}: {str(e)}')
            raise

    # Estados internos → etiqueta clara para el cliente final (decisión de
    # producto: el cliente ve lenguaje cercano, no la jerga del taller).
    _ESTADO_CLIENTE = {
        'Pendiente': 'Recibido',
        'En proceso': 'En reparación',
        'Terminado': 'Listo para recoger',
        'Entregado': 'Entregado',
    }

    def send_repair_status_update(self, to_email, cliente_nombre, reparacion_id,
                                  estado_anterior, estado_nuevo, dispositivo,
                                  descripcion, tracking_url=None, baja_url=None):
        """Actualizacion de estado de una reparacion (white-label).

        `tracking_url` (portal de seguimiento por código) y `baja_url` (opt-out
        firmado) son opcionales: si faltan, la plantilla los omite.
        """
        try:
            emisor = self._emisor()
            html = render_template(
                'emails/repair_status_update.html',
                cliente_nombre=cliente_nombre,
                reparacion_id=reparacion_id,
                estado_anterior=estado_anterior,
                estado_nuevo=estado_nuevo,
                estado_anterior_label=self._ESTADO_CLIENTE.get(estado_anterior, estado_anterior),
                estado_nuevo_label=self._ESTADO_CLIENTE.get(estado_nuevo, estado_nuevo),
                dispositivo=dispositivo,
                descripcion=descripcion,
                tracking_url=tracking_url,
                baja_url=baja_url,
                fecha_actualizacion=datetime.now().strftime('%d/%m/%Y %H:%M'),
                year=datetime.now().year,
                emisor=emisor,
            )
            self._send(
                subject=f'Actualizacion de Estado - Reparacion #{reparacion_id} - {emisor.get("nombre") or "Tu taller"}',
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
            emisor = self._emisor()
            html = render_template(
                'emails/payment_confirmation.html',
                cliente_nombre=cliente_nombre,
                reparacion_id=reparacion_id,
                precio=precio,
                descripcion=descripcion,
                fecha_pago=fecha_factura or datetime.now().strftime('%d/%m/%Y'),
                year=datetime.now().year,
                emisor=emisor,
            )
            self._send(
                subject=f'Factura - Reparacion #{reparacion_id} - {emisor.get("nombre") or "Tu taller"}',
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
            emisor = self._emisor()
            html = render_template(
                'emails/nueva_reparacion.html',
                cliente_nombre=cliente_nombre,
                reparacion_id=reparacion_id,
                dispositivo=dispositivo,
                descripcion=descripcion,
                fecha_entrada=fecha_entrada,
                year=datetime.now().year,
                emisor=emisor,
            )
            self._send(
                subject=f'Nueva Reparacion Registrada #{reparacion_id} - {emisor.get("nombre") or "Tu taller"}',
                to_email=to_email, html_body=html,
            )
            logger.info(f'Email de nueva reparacion enviado a {to_email} para reparacion {reparacion_id}')
        except Exception as e:
            logger.error(f'Error enviando email de nueva reparacion: {type(e).__name__}: {str(e)}')
            raise

    def send_bienvenida_cliente(self, to_email, cliente_nombre):
        """Email de bienvenida a un nuevo cliente."""
        try:
            emisor = self._emisor()
            html = render_template(
                'emails/bienvenida_cliente.html',
                cliente_nombre=cliente_nombre,
                year=datetime.now().year,
                emisor=emisor,
            )
            self._send(
                subject=f'Bienvenido a {emisor.get("nombre") or "tu taller"} - Servicio Tecnico',
                to_email=to_email, html_body=html,
            )
            logger.info(f'Email de bienvenida enviado a {to_email} para cliente {cliente_nombre}')
        except Exception as e:
            logger.error(f'Error enviando email de bienvenida: {type(e).__name__}: {str(e)}')
            raise

    def send_password_reset(self, to_email, reset_url, taller_nombre=None):
        """Email con el enlace de reset de contraseña (B3.1)."""
        html = render_template(
            'emails/reset_password.html',
            reset_url=reset_url, taller_nombre=taller_nombre,
            year=datetime.now().year,
        )
        self._send(
            subject='Kintsu - Restablece tu contraseña',
            to_email=to_email, html_body=html,
        )
        logger.info(f'Email de reset de contraseña enviado a {to_email}')

    def send_email_verificacion(self, to_email, verify_url, taller_nombre=None):
        """Email con el enlace de verificación de cuenta (B3.2)."""
        html = render_template(
            'emails/verificar_email.html',
            verify_url=verify_url, taller_nombre=taller_nombre,
            year=datetime.now().year,
        )
        self._send(
            subject='Kintsu - Verifica tu email',
            to_email=to_email, html_body=html,
        )
        logger.info(f'Email de verificación enviado a {to_email}')

    def send_test(self, to_email: str, cliente_nombre: str = 'Administrador') -> None:
        """Email de prueba (usa la plantilla de bienvenida). Usado por /admin/test-email."""
        html = render_template(
            'emails/bienvenida_cliente.html',
            cliente_nombre=cliente_nombre,
            year=datetime.now().year,
            emisor=self._emisor(),  # white-label: previsualiza el branding del taller
        )
        self._send(
            subject='Kintsu - Prueba de envio de email',
            to_email=to_email, html_body=html,
        )
