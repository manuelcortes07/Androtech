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
                subject=f'✅ Pago Confirmado - Reparación #{reparacion_id}',
                recipients=[to_email],
                html=html_body
            )

            # Enviar email
            self.mail.send(msg)
            logger.info(f'Email de confirmación de pago enviado a {to_email} para reparación {reparacion_id}')

        except Exception as e:
            logger.error(f'Error enviando email de confirmación de pago: {str(e)}')
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
                subject=f'🔄 Actualización de Reparación #{reparacion_id} - {estado_nuevo}',
                recipients=[to_email],
                html=html_body
            )

            # Enviar email
            self.mail.send(msg)
            logger.info(f'Email de actualización de estado enviado a {to_email} para reparación {reparacion_id}: {estado_anterior} → {estado_nuevo}')

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
                subject=f'📄 Factura - Reparación #{reparacion_id}',
                recipients=[to_email],
                html=html_body
            )

            # Enviar email
            self.mail.send(msg)
            logger.info(f'Email de factura enviado a {to_email} para reparación {reparacion_id}')

        except Exception as e:
            logger.error(f'Error enviando email de factura: {str(e)}')
            raise