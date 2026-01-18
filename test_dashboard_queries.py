#!/usr/bin/env python
"""Test directo de la lógica del dashboard sin Flask"""

import sqlite3
from datetime import datetime

db_path = "database/andro_tech.db"

try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    print("=" * 70)
    print("TEST: Lógica del Dashboard")
    print("=" * 70)
    
    # Test 1: Contar clientes
    total_clientes = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    print(f"\n✓ Total clientes: {total_clientes}")
    
    # Test 2: Contar reparaciones
    total_reparaciones = conn.execute("SELECT COUNT(*) FROM reparaciones").fetchone()[0]
    print(f"✓ Total reparaciones: {total_reparaciones}")
    
    # Test 3: Reparaciones activas
    reparaciones_activas = conn.execute("""
        SELECT COUNT(*) FROM reparaciones
        WHERE estado != 'Terminado' AND estado != 'Entregado'
    """).fetchone()[0]
    print(f"✓ Reparaciones activas: {reparaciones_activas}")
    
    # Test 4: Ingresos totales
    ingresos_total = conn.execute("""
        SELECT IFNULL(SUM(precio), 0) FROM reparaciones
        WHERE precio IS NOT NULL
    """).fetchone()[0]
    print(f"✓ Ingresos totales: {ingresos_total}€")
    
    # Test 5: Fecha de este mes
    hoy = datetime.now()
    inicio_mes = datetime(hoy.year, hoy.month, 1)
    print(f"✓ Inicio de mes: {inicio_mes.strftime('%Y-%m-%d')}")
    
    # Test 6: Ingresos de este mes
    ingresos_mes = conn.execute("""
        SELECT IFNULL(SUM(precio), 0) FROM reparaciones
        WHERE fecha_entrada >= ? AND precio IS NOT NULL
    """, (inicio_mes.strftime("%Y-%m-%d"),)).fetchone()[0]
    print(f"✓ Ingresos este mes: {ingresos_mes}€")
    
    # Test 7: Dispositivos top
    dispositivos_top = conn.execute("""
        SELECT dispositivo, COUNT(*) as cantidad
        FROM reparaciones
        WHERE dispositivo IS NOT NULL AND dispositivo != ''
        GROUP BY dispositivo
        ORDER BY cantidad DESC
        LIMIT 5
    """).fetchall()
    print(f"✓ Dispositivos top: {len(dispositivos_top)} tipos")
    for d in dispositivos_top:
        print(f"  - {d[0]}: {d[1]} reps")
    
    # Test 8: Estados
    estados = conn.execute("""
        SELECT estado, COUNT(*) as cantidad
        FROM reparaciones
        GROUP BY estado
        ORDER BY cantidad DESC
    """).fetchall()
    print(f"✓ Estados: {len(estados)} tipos")
    
    conn.close()
    
    print("\n" + "=" * 70)
    print("✅ ÉXITO: Todas las queries funcionan correctamente")
    print("=" * 70)
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
