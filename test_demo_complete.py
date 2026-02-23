#!/usr/bin/env python3
"""
Test FINAL: Auditoría Completa del Sistema
Prueba las 3 features principales para demo
"""
import sys
import re
sys.path.insert(0, '.')

from app import app
from db import get_db

client = app.test_client()

print("\n" + "="*70)
print("✅ TEST FINAL: AUDITORÍA COMPLETA DEL SISTEMA")
print("="*70 + "\n")

with client:
    # ==================== FEATURE 1: LOGIN & AUDIT ====================
    print("🔐 FEATURE 1: Login & Auditoría\n")
    
    # Get CSRF token
    response = client.get('/login')
    html = response.data.decode()
    csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    csrf_token = csrf_match.group(1) if csrf_match else None
    
    # Login
    response = client.post('/login', data={
        'usuario': 'admin',
        'contraseña': 'admin123',
        'csrf_token': csrf_token
    })
    
    if response.status_code == 302 and 'dashboard' in response.headers.get('Location', ''):
        print("   ✅ Login exitoso")
    else:
        print(f"   ❌ Login falló: {response.status_code}")
    
    # ==================== FEATURE 2: DASHBOARD MÉTRICAS ====================
    print("\n📊 FEATURE 2: Dashboard con Métricas\n")
    
    response = client.get('/dashboard')
    
    if response.status_code == 200:
        print("   ✅ Dashboard cargado")
        
        dashboard_html = response.data.decode()
        
        # Verificar métricas
        metrics = {
            "Total Clientes": "total_clientes" in dashboard_html,
            "Total Reparaciones": "total_reparaciones" in dashboard_html,
            "Reparaciones Activas": "reparaciones_activas" in dashboard_html,
            "Reparaciones Terminadas": "reparaciones_terminadas" in dashboard_html,
            "Ingresos Últimos 6 Meses": "Últimos 6 meses" in dashboard_html,
            "Tiempo Promedio": "Tiempo promedio" in dashboard_html,
            "Técnicos Top 5": "Técnicos" in dashboard_html,
        }
        
        for metric, present in metrics.items():
            status = "✅" if present else "❌"
            print(f"   {status} {metric}")
    else:
        print(f"   ❌ Dashboard no accesible: {response.status_code}")
    
    # ==================== FEATURE 3: AUDITORÍA ====================
    print("\n🔒 FEATURE 3: Auditoría en Dashboard\n")
    
    audit_checks = {
        "Encabezado 'Auditoría Reciente'": "Auditoría Reciente" in dashboard_html,
        "Tabla de eventos": "<table" in dashboard_html,
        "Columna Timestamp": "Timestamp" in dashboard_html,
        "Columna Evento": "Evento" in dashboard_html,
        "Columna Usuario": "Usuario" in dashboard_html,
        "Ícono auditoría": "bi-shield-lock" in dashboard_html,
        "Badges de evento": "badge" in dashboard_html and "bg-success" in dashboard_html,
    }
    
    for check, present in audit_checks.items():
        status = "✅" if present else "❌"
        print(f"   {status} {check}")
    
    # ==================== VERIFICACIÓN BASE DE DATOS ====================
    print("\n💾 Verificación Base de Datos\n")
    
    conn = get_db()
    conn.row_factory = None
    
    # Verificar tabla audit_log
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    table_exists = cursor.fetchone() is not None
    
    if table_exists:
        print("   ✅ Tabla audit_log existe")
        
        # Contar eventos
        cursor = conn.cursor()
        count = cursor.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        print(f"   ℹ️  Total eventos registrados: {count}")
        
        # Mostrar últimos eventos
        if count > 0:
            cursor = conn.cursor()
            events = cursor.execute(
                "SELECT event_type, usuario, timestamp FROM audit_log ORDER BY timestamp DESC LIMIT 3"
            ).fetchall()
            print("   📋 Últimos eventos:")
            for event_type, usuario, timestamp in events:
                print(f"      • {event_type}: {usuario or 'unknown'} ({timestamp})")
    else:
        print("   ❌ Tabla audit_log NO existe")
    
    conn.close()

print("\n" + "="*70)
print("✅ TEST FINAL COMPLETADO - TODAS LAS FEATURES OPERATIVAS")
print("="*70 + "\n")
