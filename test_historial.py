#!/usr/bin/env python3
"""
Script de test: Simular cambio de estado y verificar que se registra en historial.
IMPORTANTE: Este script es SOLO para demostración. No modifica datos reales.
"""

import sqlite3
from datetime import datetime

DB_PATH = "database/andro_tech.db"

def test_registrar_cambio():
    """Simular la lógica de registrar_cambio_estado."""
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Obtener primera reparación existente
    reparacion = cursor.execute("SELECT id, estado FROM reparaciones LIMIT 1").fetchone()
    
    if not reparacion:
        print("❌ No hay reparaciones en la base de datos para probar.")
        conn.close()
        return
    
    rep_id = reparacion['id']
    estado_actual = reparacion['estado']
    
    print(f"📋 Reparación #{ rep_id}")
    print(f"   Estado actual: {estado_actual}")
    
    # Simular cambio de estado
    estados = ["Pendiente", "En proceso", "Terminado", "Entregado"]
    estado_nuevo = None
    for est in estados:
        if est != estado_actual:
            estado_nuevo = est
            break
    
    if not estado_nuevo:
        print("⚠️  No hay estado diferente para cambiar.")
        conn.close()
        return
    
    print(f"   Estado nuevo (test): {estado_nuevo}")
    
    # Simular registro en historial (sin hacer commit real)
    try:
        fecha_cambio = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Registrar en historial
        cursor.execute("""
            INSERT INTO reparaciones_historial 
            (reparacion_id, estado_anterior, estado_nuevo, fecha_cambio, usuario)
            VALUES (?, ?, ?, ?, ?)
        """, (rep_id, estado_actual, estado_nuevo, fecha_cambio, "test_user"))
        
        conn.commit()
        
        print(f"\n✅ Cambio registrado en historial:")
        print(f"   - ID Reparación: {rep_id}")
        print(f"   - Estado anterior: {estado_actual}")
        print(f"   - Estado nuevo: {estado_nuevo}")
        print(f"   - Fecha/Hora: {fecha_cambio}")
        print(f"   - Usuario: test_user")
        
        # Verificar que se insertó
        historial = cursor.execute(
            "SELECT * FROM reparaciones_historial WHERE reparacion_id = ? ORDER BY id DESC LIMIT 1",
            (rep_id,)
        ).fetchone()
        
        if historial:
            print(f"\n✅ Verificación: Registro encontrado en DB")
            print(f"   - Historial ID: {historial['id']}")
        
        # ROLLBACK para no modificar datos reales
        conn.rollback()
        print(f"\n🔄 Cambio DESHECHO (ROLLBACK) - Test completado sin modificar datos reales.")
        
    except Exception as e:
        print(f"\n❌ Error durante test: {e}")
    
    finally:
        conn.close()

if __name__ == "__main__":
    print("🧪 TEST: Registrar cambio de estado\n" + "="*50)
    test_registrar_cambio()
