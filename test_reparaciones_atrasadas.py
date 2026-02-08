#!/usr/bin/env python3
"""
Test: Verificar lógica de reparaciones atrasadas en dashboard.
Atrasada = en estado 'En proceso'/'Pendiente' SIN actualización hace > 7 días.
"""

import sqlite3
from datetime import datetime, timedelta

DB_PATH = "database/andro_tech.db"

def test_reparaciones_atrasadas():
    """Simular la lógica de obtener reparaciones atrasadas."""
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    hoy = datetime.now()
    hace_7_dias = (hoy - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    
    print("📋 TEST: Reparaciones atrasadas (sin actualización hace > 7 días)\n" + "="*60)
    print(f"Hoy: {hoy.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Hace 7 días: {hace_7_dias}\n")
    
    # Query: obtener reparaciones atrasadas
    reparaciones_atrasadas = conn.execute("""
        SELECT reparaciones.*, clientes.nombre AS cliente,
               (SELECT fecha_cambio FROM reparaciones_historial 
                WHERE reparacion_id = reparaciones.id 
                ORDER BY fecha_cambio DESC LIMIT 1) AS ultima_actualizacion
        FROM reparaciones
        LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id
        WHERE reparaciones.estado IN ('En proceso', 'Pendiente')
        AND (
            SELECT fecha_cambio FROM reparaciones_historial 
            WHERE reparacion_id = reparaciones.id 
            ORDER BY fecha_cambio DESC LIMIT 1
        ) < ? 
        OR (
            SELECT COUNT(*) FROM reparaciones_historial 
            WHERE reparacion_id = reparaciones.id
        ) = 0
        ORDER BY reparaciones.id DESC
    """, (hace_7_dias,)).fetchall()
    
    if not reparaciones_atrasadas:
        print("✅ No hay reparaciones atrasadas (excelente).")
    else:
        print(f"⚠️  ALERTA: {len(reparaciones_atrasadas)} reparación(es) atrasada(s):\n")
        for r in reparaciones_atrasadas:
            print(f"  • #{r['id']} - {r['cliente'] or 'Sin cliente'} ({r['dispositivo']})")
            print(f"    Estado: {r['estado']}")
            print(f"    Última actualización: {r['ultima_actualizacion'] or 'Nunca'}")
            print()
    
    # Obtener todas las reparaciones en proceso/pendiente
    todas = conn.execute("""
        SELECT reparaciones.*, clientes.nombre AS cliente,
               (SELECT fecha_cambio FROM reparaciones_historial 
                WHERE reparacion_id = reparaciones.id 
                ORDER BY fecha_cambio DESC LIMIT 1) AS ultima_actualizacion
        FROM reparaciones
        LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id
        WHERE reparaciones.estado IN ('En proceso', 'Pendiente')
    """).fetchall()
    
    print("="*60)
    print(f"Reparaciones activas: {len(todas)}")
    print(f"Atrasadas: {len(reparaciones_atrasadas)}")
    print("✅ Test completado")
    
    conn.close()

if __name__ == "__main__":
    test_reparaciones_atrasadas()
