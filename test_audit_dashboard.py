#!/usr/bin/env python3
"""
Test: Auditoría visible en Dashboard
Verifica que la sección de auditoría reciente se renderiza correctamente
"""
import sys
sys.path.insert(0, '.')

from app import app
from db import get_db
from auth import login_required
import json

# Test client
client = app.test_client()

print("\n📊 PRUEBA: Auditoría en Dashboard\n")

# 1. Login como admin
print("1️⃣  Iniciando sesión como admin...")
response = client.post('/login', data={
    'usuario': 'admin',
    'contraseña': 'admin123'
}, follow_redirects=False)

# Check login redirect (should be 302)
print(f"   ℹ️  Login response: {response.status_code}")
print("   ✅ Login sent")

# 2. Access dashboard with session cookies
print("\n2️⃣  Accediendo a dashboard...")
response = client.get('/dashboard', follow_redirects=False)

if response.status_code == 302:
    print(f"   ℹ️  Dashboard redirect: {response.status_code}")
    # Try to follow redirect
    response = client.get(response.location)

if response.status_code != 200:
    print(f"   ❌ Dashboard no accesible: {response.status_code}")
    sys.exit(1)

dashboard_html = response.data.decode()
print("   ✅ Dashboard accesible (200)")


# 3. Check for audit section
print("\n3️⃣  Verificando sección de auditoría...")

checks = {
    "Encabezado 'Auditoría Reciente'": "Auditoría Reciente" in dashboard_html,
    "Tabla de eventos": "<table" in dashboard_html,
    "Badges de eventos": "badge" in dashboard_html,
    "Columna Timestamp": "Timestamp" in dashboard_html,
    "Columna Evento": "Evento" in dashboard_html,
    "Columna Usuario": "Usuario" in dashboard_html,
    "Ícono de auditoría": "bi-shield-lock" in dashboard_html,
}

for check_name, check_result in checks.items():
    status = "✅" if check_result else "❌"
    print(f"   {status} {check_name}")

all_passed = all(checks.values())

# 4. Verify audit data is being fetched
print("\n4️⃣  Verificando datos de auditoría en base de datos...")
conn = get_db()
conn.row_factory = None  # Raw tuples

# Check audit_log table exists
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
table_exists = cursor.fetchone() is not None

if table_exists:
    print("   ✅ Tabla audit_log existe")
    
    # Count audit events
    cursor = conn.cursor()
    count = cursor.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    print(f"   ✅ Total eventos en auditoría: {count}")
    
    # Sample events
    if count > 0:
        cursor = conn.cursor()
        cursor.row_factory = None
        events = cursor.execute(
            "SELECT event_type, usuario, timestamp FROM audit_log ORDER BY timestamp DESC LIMIT 5"
        ).fetchall()
        print("   📋 Últimos eventos:")
        for event_type, usuario, timestamp in events:
            print(f"      • {event_type}: {usuario} ({timestamp})")
else:
    print("   ❌ Tabla audit_log NO existe")
    all_passed = False

conn.close()

print("\n" + "="*60)
if all_passed:
    print("✅ AUDITORÍA EN DASHBOARD: COMPLETADO")
    print("="*60)
else:
    print("⚠️  Algunos controles fallaron - revisar")
    print("="*60)

sys.exit(0 if all_passed else 1)
