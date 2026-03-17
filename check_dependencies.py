#!/usr/bin/env python3
"""
Script para verificar que todas las dependencias están instaladas correctamente
"""

import sys
import os

def check_dependency(name, import_name=None):
    """Verificar si una dependencia está disponible"""
    if import_name is None:
        import_name = name

    try:
        __import__(import_name)
        print(f"✅ {name}: OK")
        return True
    except ImportError:
        print(f"❌ {name}: NO ENCONTRADO")
        return False

def main():
    print("🔍 Verificando dependencias de AndroTech...")
    print("=" * 50)

    # Verificar entorno virtual
    is_venv = sys.prefix != sys.base_prefix
    print(f"Entorno virtual: {'✅ ACTIVO' if is_venv else '❌ NO ACTIVO'}")
    print(f"Python executable: {sys.executable}")
    print()

    # Verificar dependencias críticas
    dependencies = [
        ("Flask", "flask"),
        ("Flask-Mail", "flask_mail"),
        ("Stripe", "stripe"),
        ("python-dotenv", "dotenv"),
        ("Werkzeug", "werkzeug"),
        ("Jinja2", "jinja2"),
        ("PDF libraries", "fpdf"),
        ("ReportLab", "reportlab"),
    ]

    all_ok = True
    for name, import_name in dependencies:
        if not check_dependency(name, import_name):
            all_ok = False

    print()
    if all_ok:
        print("🎉 ¡Todas las dependencias están instaladas correctamente!")
        print()
        print("Para ejecutar la aplicación:")
        print("1. Asegúrate de que el entorno virtual esté activado")
        print("2. Ejecuta: python app.py")
        print()
        print("Si VS Code aún marca errores en amarillo:")
        print("- Presiona Ctrl+Shift+P")
        print("- Busca 'Python: Select Interpreter'")
        print("- Selecciona './venv/Scripts/python.exe'")
    else:
        print("❌ Faltan algunas dependencias.")
        print("Ejecuta: pip install -r requirements.txt")

if __name__ == '__main__':
    main()