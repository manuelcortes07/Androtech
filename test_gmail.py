#!/usr/bin/env python3
"""
Script para probar configuración de Gmail específicamente
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from utils.email_service import EmailService
from flask_mail import Mail

def test_gmail_config():
    """Probar configuración específica de Gmail"""
    print("🔍 Probando configuración de Gmail...")

    # Crear app Flask con configuración de Gmail
    app = Flask(__name__)

    # Configuración específica para Gmail
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USE_SSL'] = False
    app.config['MAIL_USERNAME'] = input("Ingresa tu email de Gmail: ")
    app.config['MAIL_PASSWORD'] = input("Ingresa tu contraseña de aplicación de Gmail: ")
    app.config['MAIL_DEFAULT_SENDER'] = 'noreply@androtech.com'
    app.config['MAIL_DEFAULT_CHARSET'] = 'utf-8'

    # Inicializar mail
    mail = Mail(app)

    # Crear servicio de email
    email_service = EmailService(mail)

    print("\n📧 Enviando email de prueba con Gmail...")

    try:
        with app.app_context():
            email_service.send_payment_confirmation(
                to_email=input("Ingresa email de destino para prueba: "),
                cliente_nombre='Usuario de Prueba',
                reparacion_id=999,
                precio=50.00,
                descripcion='Prueba de configuración Gmail'
            )
        print("✅ ¡Email enviado exitosamente con Gmail!")
        return True

    except Exception as e:
        print(f"❌ Error con Gmail: {type(e).__name__}: {str(e)}")

        if "535" in str(e):
            print("\n🔐 Posibles causas del error 535:")
            print("1. La contraseña es incorrecta")
            print("2. No usaste 'Contraseña de aplicación' (si tienes 2FA)")
            print("3. La cuenta tiene restricciones de seguridad")
            print("4. Gmail bloqueó el acceso")

        elif "534" in str(e):
            print("\n🔐 Error de autenticación - necesitas:")
            print("1. Activar 2FA en tu cuenta Gmail")
            print("2. Generar una 'Contraseña de aplicación'")
            print("3. Usar esa contraseña en lugar de tu contraseña normal")

        return False

if __name__ == '__main__':
    print("🚀 Probador de Gmail para AndroTech")
    print("=" * 50)
    print("Este script probará específicamente Gmail")
    print("Asegúrate de tener:")
    print("1. Una cuenta Gmail válida")
    print("2. 2FA activado (recomendado)")
    print("3. Una 'Contraseña de aplicación' generada")
    print("=" * 50)

    success = test_gmail_config()

    if success:
        print("\n🎉 ¡Gmail funciona! Puedes usar esta configuración.")
    else:
        print("\n💡 Recomendaciones:")
        print("1. Ve a https://myaccount.google.com/security")
        print("2. Activa la verificación en 2 pasos")
        print("3. Genera una 'Contraseña de aplicación'")
        print("4. Usa esa contraseña de 16 caracteres aquí")
        print("5. Si no funciona, considera usar Outlook o SendGrid")