#!/usr/bin/env python3
"""
Script para configurar webhooks de Stripe
"""

def configure_webhooks():
    """Configurar webhooks para que los pagos se guarden automáticamente"""

    print("🔗 CONFIGURACIÓN DE WEBHOOKS DE STRIPE")
    print("=" * 50)
    print("Para que los pagos se guarden automáticamente, necesitas configurar webhooks.")
    print()

    print("📋 PASOS PARA CONFIGURAR WEBHOOKS:")
    print()
    print("1. Ve a https://dashboard.stripe.com/test/webhooks")
    print("2. Haz clic en 'Add endpoint'")
    print("3. Configura:")
    print("   - URL: http://127.0.0.1:5000/stripe/webhook (para desarrollo local)")
    print("   - Events: Selecciona 'checkout.session.completed'")
    print("4. Copia el 'Webhook Signing Secret' que te dan")
    print()

    webhook_secret = input("Pega aquí el Webhook Signing Secret: ").strip()

    if not webhook_secret:
        print("❌ No se configuró el webhook secret")
        return

    # Leer .env actual
    try:
        with open('.env', 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        content = ""

    # Agregar o reemplazar STRIPE_WEBHOOK_SECRET
    import re

    if 'STRIPE_WEBHOOK_SECRET=' in content:
        content = re.sub(
            r'STRIPE_WEBHOOK_SECRET=.*',
            f'STRIPE_WEBHOOK_SECRET={webhook_secret}',
            content
        )
    else:
        content += f'\nSTRIPE_WEBHOOK_SECRET={webhook_secret}\n'

    # Escribir archivo actualizado
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(content)

    print("\n✅ ¡Webhook configurado correctamente!")
    print("   Los pagos ahora se guardarán automáticamente")

    print("\n📋 PARA PRODUCCIÓN:")
    print("Cuando subas a producción, cambia la URL del webhook:")
    print("- De: http://127.0.0.1:5000/stripe/webhook")
    print("- A: https://tu-dominio.com/stripe/webhook")

if __name__ == '__main__':
    configure_webhooks()