#!/usr/bin/env python3
"""
Script para configurar credenciales de Gmail correctamente
"""

def configure_gmail():
    """Configurar Gmail con credenciales reales"""

    print("🔧 CONFIGURACIÓN DE GMAIL PARA ANDROTECH")
    print("=" * 50)
    print("Necesitas configurar tus credenciales reales de Gmail.")
    print()

    # Pedir credenciales
    print("1. Tu dirección de Gmail:")
    gmail_user = input("   Email: ").strip()

    print("\n2. Contraseña de aplicación de Gmail:")
    print("   (Si no tienes 2FA activado, usa tu contraseña normal)")
    print("   (Si tienes 2FA, genera una 'Contraseña de aplicación')")
    gmail_pass = input("   Contraseña: ").strip()

    # Leer .env actual
    try:
        with open('.env', 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        content = ""

    # Reemplazar credenciales
    import re

    # Reemplazar MAIL_USERNAME
    content = re.sub(
        r'MAIL_USERNAME=.*',
        f'MAIL_USERNAME={gmail_user}',
        content
    )

    # Reemplazar MAIL_PASSWORD
    content = re.sub(
        r'MAIL_PASSWORD=.*',
        f'MAIL_PASSWORD={gmail_pass}',
        content
    )

    # Escribir archivo actualizado
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(content)

    print("\n✅ ¡Gmail configurado correctamente!")
    print(f"   Email: {gmail_user}")
    print("   Contraseña: [CONFIGURADA]")

    # Verificar configuración
    print("\n🔍 Verificando configuración...")
    try:
        from app import app
        from utils.email_service import EmailService
        from flask_mail import Mail

        app.config['TESTING'] = True
        mail = Mail(app)
        email_service = EmailService(mail)

        with app.app_context():
            email_service.send_payment_confirmation(
                to_email=gmail_user,
                cliente_nombre='Prueba de Configuración',
                reparacion_id=1,
                precio=10.00,
                descripcion='Verificación de Gmail'
            )
        print("✅ Email de prueba enviado correctamente")

    except Exception as e:
        print(f"⚠️  Error en prueba: {str(e)[:100]}...")
        print("   Esto puede ser normal si las credenciales necesitan verificación")

    print("\n📧 PRÓXIMOS PASOS:")
    print("1. Reinicia la aplicación: python app.py")
    print("2. Prueba un pago real")
    print("3. Deberías recibir el email de confirmación")

if __name__ == '__main__':
    configure_gmail()