#!/usr/bin/env python3
"""
Script para diagnosticar y solucionar problemas de pagos y emails
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def check_configuration():
    """Verificar configuración actual"""
    from dotenv import load_dotenv
    load_dotenv()

    print("🔍 DIAGNÓSTICO DE CONFIGURACIÓN")
    print("=" * 50)

    # Email
    mail_user = os.getenv('MAIL_USERNAME', '')
    mail_pass = os.getenv('MAIL_PASSWORD', '')

    print("📧 CONFIGURACIÓN DE EMAIL:")
    if mail_user == 'tu-email@gmail.com':
        print("❌ MAIL_USERNAME: Usando placeholder (configurar email real)")
    else:
        print(f"✅ MAIL_USERNAME: {mail_user}")

    if not mail_pass or mail_pass == 'tu-contraseña-app':
        print("❌ MAIL_PASSWORD: No configurado o usando placeholder")
    else:
        print("✅ MAIL_PASSWORD: Configurado")

    # Stripe
    stripe_key = os.getenv('STRIPE_SECRET_KEY', '')
    stripe_webhook = os.getenv('STRIPE_WEBHOOK_SECRET', '')

    print("\n💳 CONFIGURACIÓN DE STRIPE:")
    if stripe_key:
        print("✅ STRIPE_SECRET_KEY: Configurado")
    else:
        print("❌ STRIPE_SECRET_KEY: No configurado")

    if stripe_webhook:
        print("✅ STRIPE_WEBHOOK_SECRET: Configurado")
    else:
        print("❌ STRIPE_WEBHOOK_SECRET: No configurado (webhooks no funcionarán)")

    return mail_user != 'tu-email@gmail.com' and mail_pass and mail_pass != 'tu-contraseña-app'

def test_email():
    """Probar envío de email"""
    print("\n📧 PRUEBA DE EMAIL:")
    try:
        from app import app
        from utils.email_service import EmailService
        from flask_mail import Mail

        # Configurar app
        app.config['TESTING'] = True
        mail = Mail(app)
        email_service = EmailService(mail)

        with app.app_context():
            email_service.send_payment_confirmation(
                to_email='test@example.com',
                cliente_nombre='Usuario de Prueba',
                reparacion_id=999,
                precio=50.00,
                descripcion='Prueba de funcionamiento'
            )
        print("✅ Email enviado correctamente (modo prueba)")
        return True
    except Exception as e:
        print(f"❌ Error enviando email: {e}")
        return False

def check_webhook_setup():
    """Verificar configuración de webhooks"""
    print("\n🔗 CONFIGURACIÓN DE WEBHOOKS:")

    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET', '')
    if not webhook_secret:
        print("❌ No hay STRIPE_WEBHOOK_SECRET configurado")
        print("   Los pagos no se guardarán automáticamente")
        print("   Solución: Configurar webhook en Stripe Dashboard")
        return False

    print("✅ STRIPE_WEBHOOK_SECRET configurado")
    print("   Los webhooks deberían funcionar")
    return True

def main():
    print("🔧 DIAGNÓSTICO COMPLETO - AndroTech")
    print("=" * 50)

    # Verificar configuración
    email_ok = check_configuration()

    # Probar email
    email_test_ok = test_email()

    # Verificar webhooks
    webhook_ok = check_webhook_setup()

    print("\n" + "=" * 50)
    print("📋 RESUMEN:")

    if email_ok and email_test_ok:
        print("✅ EMAIL: Configurado y funcionando")
    else:
        print("❌ EMAIL: Problemas de configuración")

    if webhook_ok:
        print("✅ WEBHOOKS: Configurados")
    else:
        print("❌ WEBHOOKS: No configurados (pagos no se guardan)")

    print("\n💡 SOLUCIONES:")

    if not email_ok:
        print("1. Configurar credenciales Gmail reales en .env")
        print("   - MAIL_USERNAME = tu-email@gmail.com")
        print("   - MAIL_PASSWORD = contraseña-de-aplicación")

    if not webhook_ok:
        print("2. Configurar webhook en Stripe Dashboard:")
        print("   - URL: http://tu-dominio/stripe/webhook")
        print("   - Eventos: checkout.session.completed")
        print("   - Copiar el 'Webhook Signing Secret'")

    if not email_test_ok:
        print("3. Verificar configuración de Gmail y reintentar")

if __name__ == '__main__':
    main()