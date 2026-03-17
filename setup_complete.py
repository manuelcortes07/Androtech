#!/usr/bin/env python3
"""
Script maestro para configurar completamente AndroTech
"""

def main():
    print("🚀 CONFIGURACIÓN COMPLETA DE ANDROTECH")
    print("=" * 50)
    print("Este script te ayudará a configurar todo lo necesario.")
    print()

    print("📋 PROBLEMAS IDENTIFICADOS:")
    print("1. ❌ Gmail no configurado (emails no se envían)")
    print("2. ❌ Webhooks no configurados (pagos no se guardan)")
    print()

    # Opción 1: Configurar Gmail
    print("¿Quieres configurar Gmail ahora? (s/n)")
    if input().lower().startswith('s'):
        print("\n" + "="*30 + " CONFIGURACIÓN DE GMAIL " + "="*30)
        import subprocess
        subprocess.run([sys.executable, 'setup_gmail.py'])

    # Opción 2: Configurar Webhooks
    print("\n¿Quieres configurar webhooks de Stripe? (s/n)")
    if input().lower().startswith('s'):
        print("\n" + "="*30 + " CONFIGURACIÓN DE WEBHOOKS " + "="*30)
        subprocess.run([sys.executable, 'setup_webhooks.py'])

    # Verificación final
    print("\n" + "="*30 + " VERIFICACIÓN FINAL " + "="*30)
    subprocess.run([sys.executable, 'diagnose_issues.py'])

    print("\n" + "="*50)
    print("🎉 CONFIGURACIÓN COMPLETADA")
    print()
    print("📋 PARA PROBAR:")
    print("1. Reinicia la aplicación: python app.py")
    print("2. Ve a /consulta e intenta un pago")
    print("3. Deberías recibir email Y el pago se debería guardar")
    print()
    print("💡 Si algo no funciona, ejecuta: python diagnose_issues.py")

if __name__ == '__main__':
    import sys
    main()