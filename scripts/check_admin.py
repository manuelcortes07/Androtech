#!/usr/bin/env python3
"""
Test: Revisar usuario admin
"""
import sys
sys.path.insert(0, '.')

from db import get_db

conn = get_db()
conn.row_factory = None

print("\n🔍 Usuarios en base de datos:\n")

cursor = conn.cursor()
cursor.execute("SELECT usuario, rol FROM usuarios")
usuarios = cursor.fetchall()

for usuario, rol in usuarios:
    print(f"   • {usuario} (rol: {rol})")

print()

# Intentar verificar hash
from werkzeug.security import check_password_hash

cursor = conn.cursor()
user = cursor.execute("SELECT * FROM usuarios WHERE usuario = ?", ('admin',)).fetchone()

if user:
    print(f"✅ Usuario 'admin' encontrado")
    print(f"   Contraseña hash: {user[1][:20]}...")
    
    # Test password
    test_password = 'admin123'
    result = check_password_hash(user[1], test_password)
    print(f"   check_password_hash('admin123'): {result}")
    
    if not result:
        print("\n   ⚠️  La contraseña no coincide. Intentando generar nuevo hash...")
        from werkzeug.security import generate_password_hash
        new_hash = generate_password_hash('admin123')
        print(f"   Nuevo hash: {new_hash[:30]}...")
        
        # Actualizar
        cursor.execute("UPDATE usuarios SET contraseña = ? WHERE usuario = ?", (new_hash, 'admin'))
        conn.commit()
        print("   ✅ Contraseña actualizada")
else:
    print("❌ Usuario 'admin' no encontrado")

conn.close()
