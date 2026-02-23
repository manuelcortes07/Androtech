#!/usr/bin/env python3
"""
Test: Verificar query usuarios 
"""
import sys
sys.path.insert(0, '.')

from db import get_db
from werkzeug.security import check_password_hash

conn = get_db()
user = conn.execute("SELECT * FROM usuarios WHERE usuario = ?", ('admin',)).fetchone()

print(f"user: {user}")
print(f"type(user): {type(user)}")
print(f"user['usuario']: {user['usuario']}")
print(f"user['contraseña']: {user['contraseña'][:30]}...")

# Test password
result = check_password_hash(user["contraseña"], 'admin123')
print(f"\ncheck_password_hash(user['contraseña'], 'admin123'): {result}")

conn.close()
