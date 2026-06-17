"""Script de diagnóstico: imprime el hash de la contraseña del admin.

Ejecutar desde la raíz del repo: python scripts/check_pw.py
(Actualizado en Fase 1.9: usa la capa SQLAlchemy; db.py ya no existe.)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from database import get_session
from models import Usuario

with get_session() as s:
    user = s.scalars(select(Usuario).where(Usuario.usuario == "admin")).first()
    if user:
        print(f"Admin user: {user.usuario}")
        print(f"Password hash starts with: {user.password[:20]}")
    else:
        print("Usuario 'admin' no encontrado")
