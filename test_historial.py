#!/usr/bin/env python3
"""
Script de test: Simular cambio de estado y verificar que se registra en historial.
IMPORTANTE: Este script es SOLO para demostración. No modifica datos reales.
"""

import sqlite3
from datetime import datetime
from historial import registrar_cambio_estado

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
    
    # Utilizar el helper importado para registrar el cambio
    registrado = registrar_cambio_estado(conn, rep_id, estado_nuevo, usuario="test_user")
    if registrado:
        print(f"\n✅ Cambio registrado en historial (helper devuelto True). \n   - ID Reparación: {rep_id}\n   - Estado anterior: {estado_actual}\n   - Estado nuevo: {estado_nuevo}\n   - Usuario: test_user")
        # Verificar que se insertó directamente
        historial = cursor.execute(
            "SELECT * FROM reparaciones_historial WHERE reparacion_id = ? ORDER BY id DESC LIMIT 1",
            (rep_id,)
        ).fetchone()
        if historial:
            print(f"\n✅ Verificación: Registro encontrado en DB")
            print(f"   - Historial ID: {historial['id']}")
    else:
        print("⚠️  El helper indicó que no se registró el cambio (posible mismo estado).")
    # ROLLBACK para no modificar datos reales
    conn.rollback()
    print(f"\n🔄 Cambio DESHECHO (ROLLBACK) - Test completado sin modificar datos reales.")
    conn.close()

if __name__ == "__main__":
    print("🧪 TEST: Registrar cambio de estado\n" + "="*50)
    test_registrar_cambio()
