#!/usr/bin/env python3
"""
Script de prueba para el sistema de email de AndroTech
Ejecutar después de configurar las variables de entorno de email
"""

import os
import sys
from datetime import datetime

# Agregar el directorio raíz al path para importar módulos locales
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from flask_mail import Mail
from utils.email_service import EmailService

def test_email_service():
    """Probar el servicio de email"""

    print("🧪 Probando sistema de email de AndroTech")
    print("=" * 50)

    # Verificar variables de entorno
    required_vars = ['MAIL_SERVER', 'MAIL_USERNAME', 'MAIL_PASSWORD']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]

    if missing_vars:
        print(f"❌ Variables de entorno faltantes: {', '.join(missing_vars)}")
        print("Ejecuta: .\\configure_email.ps1")
        return False

    print("✅ Variables de entorno configuradas")

    # Crear app Flask mínima para testing
    app = Flask(__name__)

    # Configurar Flask-Mail
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'test@androtech.com')

    # Configurar templates folder
    app.template_folder = 'templates'

    mail = Mail(app)
    email_service = EmailService(mail)

    # Probar envío de email de prueba
    test_email = os.environ.get('MAIL_USERNAME')  # Enviar a nosotros mismos

    if not test_email:
        print("❌ No se puede determinar email de prueba")
        return False

    print(f"📧 Enviando email de prueba a: {test_email}")

    try:
        with app.app_context():
            # Enviar email de confirmación de pago de prueba
            email_service.send_payment_confirmation(
                to_email=test_email,
                cliente_nombre="Cliente de Prueba",
                reparacion_id=999,
                precio=99.99,
                descripcion="iPhone 12 Pro Max - Reparación de pantalla"
            )

            print("✅ Email de confirmación de pago enviado exitosamente")

            # Enviar email de actualización de estado de prueba
            email_service.send_repair_status_update(
                to_email=test_email,
                cliente_nombre="Cliente de Prueba",
                reparacion_id=999,
                estado_anterior="En Progreso",
                estado_nuevo="Terminado",
                dispositivo="iPhone 12 Pro Max",
                descripcion="Reparación de pantalla completada"
            )

            print("✅ Email de actualización de estado enviado exitosamente")

    except Exception as e:
        print(f"❌ Error enviando emails: {str(e)}")
        return False

    print("")
    print("🎉 ¡Sistema de email funcionando correctamente!")
    print("Revisa tu bandeja de entrada (y spam) para ver los emails de prueba.")
    return True

if __name__ == "__main__":
    success = test_email_service()
    sys.exit(0 if success else 1)