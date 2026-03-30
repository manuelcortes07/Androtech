"""
Sistema de Email Automático para AndroTech
Maneja notificaciones por email para pagos, estados de reparación, etc.
"""

import os
from flask import current_app, render_template
from flask_mail import Mail, Message
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class EmailService:
    """Servicio de email para notificaciones automáticas"""

    def __init__(self, mail_instance):
        self.mail = mail_instance

    def send_payment_confirmation(self, to_email, cliente_nombre, reparacion_id, precio, descripcion):
        """Enviar confirmación de pago por email"""
        try:
            logger.debug(f"Enviando email de confirmacion de pago a reparacion {reparacion_id}")
            # Renderizar template HTML
            html_body = render_template(
                'emails/payment_confirmation.html',
                cliente_nombre=cliente_nombre,
                reparacion_id=reparacion_id,
                precio=precio,
                descripcion=descripcion,
                fecha_pago=datetime.now().strftime('%d/%m/%Y %H:%M'),
                year=datetime.now().year
            )

            # Crear mensaje
            msg = Message(
                subject='Payment Confirmed - Repair',
                recipients=[to_email],
                charset='utf-8'
            )
            msg.html = html_body
            msg.content_type = 'text/html; charset=utf-8'
            # Enviar email
            self.mail.send(msg)
            logger.info(f'Email de confirmacion de pago enviado a {to_email} para reparacion {reparacion_id}')

        except Exception as e:
            logger.error(f'Error enviando email de confirmacion de pago: {type(e).__name__}: {str(e)}')
            raise

    def send_repair_status_update(self, to_email, cliente_nombre, reparacion_id, estado_anterior, estado_nuevo, dispositivo, descripcion):
        """Enviar actualización de estado de reparación por email"""
        try:
            # Renderizar template HTML
            html_body = render_template(
                'emails/repair_status_update.html',
                cliente_nombre=cliente_nombre,
                reparacion_id=reparacion_id,
                estado_anterior=estado_anterior,
                estado_nuevo=estado_nuevo,
                dispositivo=dispositivo,
                descripcion=descripcion,
                fecha_actualizacion=datetime.now().strftime('%d/%m/%Y %H:%M'),
                year=datetime.now().year
            )

            # Crear mensaje
            msg = Message(
                subject=f'Repair Status Update #{reparacion_id} - {estado_nuevo}',
                recipients=[to_email],
                charset='utf-8'
            )
            msg.html = html_body
            msg.content_type = 'text/html; charset=utf-8'
            # Enviar email
            self.mail.send(msg)
            logger.info(f'Email de actualizacion de estado enviado a {to_email} para reparacion {reparacion_id}: {estado_anterior} -> {estado_nuevo}')

        except Exception as e:
            logger.error(f'Error enviando email de actualización de estado: {str(e)}')
            raise

    def send_invoice(self, to_email, cliente_nombre, reparacion_id, precio, descripcion, fecha_factura=None):
        """Enviar factura por email"""
        try:
            # Renderizar template HTML (usando la misma plantilla de confirmación de pago por ahora)
            html_body = render_template(
                'emails/payment_confirmation.html',
                cliente_nombre=cliente_nombre,
                reparacion_id=reparacion_id,
                precio=precio,
                descripcion=descripcion,
                fecha_pago=fecha_factura or datetime.now().strftime('%d/%m/%Y'),
                year=datetime.now().year
            )

            # Crear mensaje
            msg = Message(
                subject=f'Factura - Reparacion #{reparacion_id}',
                recipients=[to_email],
                charset='utf-8'
            )
            msg.html = html_body
            msg.content_type = 'text/html; charset=utf-8'
            # Enviar email
            self.mail.send(msg)
            logger.info(f'Email de factura enviado a {to_email} para reparación {reparacion_id}')

        except Exception as e:
            logger.error(f'Error enviando email de factura: {str(e)}')
            raise