#!/usr/bin/env python3
"""
Script para probar el envío real de emails con Gmail
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from utils.email_service import EmailService
from flask_mail import Mail

def test_real_email():
    """Probar envío real de email"""
    print("🚀 Probando envío REAL de email con Gmail...")

    # Crear app Flask
    app = Flask(__name__)

    # Cargar configuración desde .env
    from dotenv import load_dotenv
    load_dotenv()

    # Configurar Flask-Mail
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true'
    app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'false').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@androtech.com')
    app.config['MAIL_DEFAULT_CHARSET'] = 'utf-8'

    # Inicializar mail
    mail = Mail(app)

    # Crear servicio de email
    email_service = EmailService(mail)

    # Pedir datos de prueba
    to_email = input("Ingresa el email de destino para la prueba: ")
    cliente_nombre = input("Ingresa el nombre del cliente: ")

    print(f"\n📧 Enviando email REAL a {to_email}...")

    try:
        with app.app_context():
            email_service.send_payment_confirmation(
                to_email=to_email,
                cliente_nombre=cliente_nombre,
                reparacion_id=999,
                precio=50.00,
                descripcion='Prueba de envío real con Gmail'
            )
        print("✅ ¡Email enviado exitosamente!")
        print(f"📬 Revisa la bandeja de entrada de {to_email}")
        return True

    except Exception as e:
        print(f"❌ Error enviando email: {type(e).__name__}: {str(e)}")

        if "535" in str(e):
            print("\n🔐 Error de autenticación:")
            print("- Verifica que MAIL_USERNAME y MAIL_PASSWORD sean correctos")
            print("- Si tienes 2FA, usa una 'Contraseña de aplicación'")
            print("- Revisa que no haya espacios en la contraseña")

        elif "534" in str(e):
            print("\n🔐 Necesitas 'Contraseña de aplicación':")
            print("1. Ve a https://myaccount.google.com/security")
            print("2. Activa verificación en 2 pasos")
            print("3. Crea una contraseña de aplicación")
            print("4. Usa esa contraseña en MAIL_PASSWORD")

        return False

if __name__ == '__main__':
    print("📧 Probador de Envío Real de Emails - AndroTech")
    print("=" * 50)
    print("Este script enviará un email REAL usando tu configuración de Gmail")
    print("Asegúrate de tener configurado MAIL_USERNAME y MAIL_PASSWORD en .env")
    print("=" * 50)

    success = test_real_email()

    if success:
        print("\n🎉 ¡El sistema de email funciona perfectamente!")
        print("Los emails de pago se enviarán automáticamente.")
    else:
        print("\n💡 Revisa la configuración y vuelve a intentar.")