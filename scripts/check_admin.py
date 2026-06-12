#!/usr/bin/env python3
"""
Test: Revisar usuario admin

Ejecutar desde la raíz del repo: python scripts/check_admin.py
(Actualizado en Fase 1.9: usa la capa SQLAlchemy; db.py ya no existe.)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_session
from models import Usuario

with get_session() as s:
    print("\n🔍 Usuarios en base de datos:\n")
    for u in s.scalars(select(Usuario)).all():
        print(f"   • {u.usuario} (rol: {u.rol})")
    print()

    user = s.scalars(select(Usuario).where(Usuario.usuario == 'admin')).first()

    if user:
        print("✅ Usuario 'admin' encontrado")
        print(f"   Contraseña hash: {user.password[:20]}...")

        # Test password
        test_password = 'admin123'
        result = check_password_hash(user.password, test_password)
        print(f"   check_password_hash('admin123'): {result}")

        if not result:
            print("\n   ⚠️  La contraseña no coincide. Intentando generar nuevo hash...")
            new_hash = generate_password_hash('admin123')
            print(f"   Nuevo hash: {new_hash[:30]}...")

            # Actualizar
            user.password = new_hash
            s.commit()
            print("   ✅ Contraseña actualizada")
    else:
        print("❌ Usuario 'admin' no encontrado")
