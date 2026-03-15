#!/usr/bin/env python3
"""
Script para alternar entre configuraciones de email (Gmail/Outlook)
"""

import os
import re

def switch_to_gmail():
    """Cambiar configuración a Gmail"""
    print("🔄 Cambiando a configuración de Gmail...")

    # Leer .env actual
    with open('.env', 'r', encoding='utf-8') as f:
        content = f.read()

    # Comentar Outlook y descomentar Gmail
    content = re.sub(r'# Configuracion de Email - Gmail.*?\n(# MAIL_SERVER=.*?\n# MAIL_PORT=.*?\n# MAIL_USE_TLS=.*?\n# MAIL_USE_SSL=.*?\n# MAIL_USERNAME=.*?\n# MAIL_PASSWORD=.*?\n# MAIL_DEFAULT_SENDER=.*?\n)', r'# Configuracion de Email - Gmail (descomenta para usar Gmail)\nMAIL_SERVER=smtp.gmail.com\nMAIL_PORT=587\nMAIL_USE_TLS=true\nMAIL_USE_SSL=false\nMAIL_USERNAME=tu-email@gmail.com\nMAIL_PASSWORD=tu-contraseña-app\nMAIL_DEFAULT_SENDER=noreply@androtech.com\n', content)

    content = re.sub(r'# Configuracion de Email - Outlook/Hotmail.*?\n(MAIL_SERVER=.*?\nMAIL_PORT=.*?\nMAIL_USE_TLS=.*?\nMAIL_USE_SSL=.*?\nMAIL_USERNAME=.*?\nMAIL_PASSWORD=.*?\nMAIL_DEFAULT_SENDER=.*?\n)', r'# Configuracion de Email - Outlook/Hotmail\n# MAIL_SERVER=smtp-mail.outlook.com\n# MAIL_PORT=587\n# MAIL_USE_TLS=true\n# MAIL_USE_SSL=false\n# MAIL_USERNAME=manuelcortescontreras11@outlook.com\n# MAIL_PASSWORD=Manuelcortes1*\n# MAIL_DEFAULT_SENDER=noreply@androtech.com\n', content)

    # Escribir cambios
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ Configuración cambiada a Gmail")
    print("⚠️  Recuerda:")
    print("   1. Configurar MAIL_USERNAME y MAIL_PASSWORD en .env")
    print("   2. Usar 'Contraseña de aplicación' si tienes 2FA")
    print("   3. Probar con: python test_gmail.py")

def switch_to_outlook():
    """Cambiar configuración a Outlook"""
    print("🔄 Cambiando a configuración de Outlook...")

    # Leer .env actual
    with open('.env', 'r', encoding='utf-8') as f:
        content = f.read()

    # Comentar Gmail y descomentar Outlook
    content = re.sub(r'# Configuracion de Email - Gmail.*?\n(MAIL_SERVER=.*?\nMAIL_PORT=.*?\nMAIL_USE_TLS=.*?\nMAIL_USE_SSL=.*?\nMAIL_USERNAME=.*?\nMAIL_PASSWORD=.*?\nMAIL_DEFAULT_SENDER=.*?\n)', r'# Configuracion de Email - Gmail (descomenta para usar Gmail)\n# MAIL_SERVER=smtp.gmail.com\n# MAIL_PORT=587\n# MAIL_USE_TLS=true\n# MAIL_USE_SSL=false\n# MAIL_USERNAME=tu-email@gmail.com\n# MAIL_PASSWORD=tu-contraseña-app\n# MAIL_DEFAULT_SENDER=noreply@androtech.com\n', content)

    content = re.sub(r'# Configuracion de Email - Outlook/Hotmail.*?\n(# MAIL_SERVER=.*?\n# MAIL_PORT=.*?\n# MAIL_USE_TLS=.*?\n# MAIL_USE_SSL=.*?\n# MAIL_USERNAME=.*?\n# MAIL_PASSWORD=.*?\n# MAIL_DEFAULT_SENDER=.*?\n)', r'# Configuracion de Email - Outlook/Hotmail\nMAIL_SERVER=smtp-mail.outlook.com\nMAIL_PORT=587\nMAIL_USE_TLS=true\nMAIL_USE_SSL=false\nMAIL_USERNAME=manuelcortescontreras11@outlook.com\nMAIL_PASSWORD=Manuelcortes1*\nMAIL_DEFAULT_SENDER=noreply@androtech.com\n', content)

    # Escribir cambios
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ Configuración cambiada a Outlook")
    print("✅ Outlook ya está configurado y listo para usar")

if __name__ == '__main__':
    print("🔄 Alternador de Configuración de Email - AndroTech")
    print("=" * 55)
    print("1. Cambiar a Gmail")
    print("2. Cambiar a Outlook")
    print("3. Ver configuración actual")
    print("=" * 55)

    choice = input("Elige una opción (1-3): ").strip()

    if choice == '1':
        switch_to_gmail()
    elif choice == '2':
        switch_to_outlook()
    elif choice == '3':
        print("\n📄 Configuración actual en .env:")
        with open('.env', 'r', encoding='utf-8') as f:
            print(f.read())
    else:
        print("❌ Opción inválida")