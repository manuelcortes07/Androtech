#!/usr/bin/env python3
"""
Script de prueba para el sistema de email de AndroTech
Prueba el servicio de email sin enviar emails reales
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from utils.email_service import EmailService
from flask_mail import Mail

# Crear app Flask
app = Flask(__name__)

# Configurar Flask-Mail (configuración dummy para pruebas)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'test@example.com'
app.config['MAIL_PASSWORD'] = 'dummy_password'
app.config['MAIL_DEFAULT_SENDER'] = 'test@example.com'
app.config['MAIL_DEFAULT_CHARSET'] = 'utf-8'

# Inicializar mail
mail = Mail(app)

# Crear servicio de email
email_service = EmailService(mail)

def test_payment_confirmation():
    """Probar envío de confirmación de pago"""
    print("\n=== PRUEBA: Confirmación de Pago ===")
    try:
        email_service.send_payment_confirmation(
            to_email='cliente@example.com',
            cliente_nombre='Juan Pérez',
            reparacion_id=123,
            precio=150.00,
            descripcion='Reparación de pantalla iPhone 12'
        )
        print("✅ Confirmación de pago: ÉXITO")
    except Exception as e:
        print(f"❌ Confirmación de pago: ERROR - {e}")

def test_repair_status_update():
    """Probar envío de actualización de estado"""
    print("\n=== PRUEBA: Actualización de Estado ===")
    try:
        email_service.send_repair_status_update(
            to_email='cliente@example.com',
            cliente_nombre='María García',
            reparacion_id=456,
            estado_anterior='En Progreso',
            estado_nuevo='Completado',
            dispositivo='Samsung Galaxy S21',
            descripcion='Reparación de batería completada'
        )
        print("✅ Actualización de estado: ÉXITO")
    except Exception as e:
        print(f"❌ Actualización de estado: ERROR - {e}")

def test_invoice():
    """Probar envío de factura"""
    print("\n=== PRUEBA: Envío de Factura ===")
    try:
        email_service.send_invoice(
            to_email='cliente@example.com',
            cliente_nombre='Carlos López',
            reparacion_id=789,
            precio=200.00,
            descripcion='Reparación completa de motherboard'
        )
        print("✅ Envío de factura: ÉXITO")
    except Exception as e:
        print(f"❌ Envío de factura: ERROR - {e}")

if __name__ == '__main__':
    print("🚀 Iniciando pruebas del sistema de email de AndroTech")
    print("Nota: Los emails se imprimen en consola, no se envían realmente")

    with app.app_context():
        test_payment_confirmation()
        test_repair_status_update()
        test_invoice()

    print("\n🎉 Pruebas completadas!")
    print("\nPara activar el envío real de emails:")
    print("1. Configura credenciales SMTP válidas en .env")
    print("2. Descomenta las líneas comentadas en utils/email_service.py")
    print("3. Reinicia la aplicación")