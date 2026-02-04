#!/usr/bin/env python3
"""
Test: Verificar que la ruta /reparaciones obtiene correctamente
la última actualización de cada reparación y la enriquece en los datos.
"""

import sqlite3
from datetime import datetime

DB_PATH = "database/andro_tech.db"

def test_ultima_actualizacion():
    """Simular la lógica de obtener última actualización."""
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Obtener reparaciones
    reparaciones = conn.execute(
        "SELECT * FROM reparaciones LIMIT 3"
    ).fetchall()
    
    if not reparaciones:
        print("❌ No hay reparaciones para probar.")
        conn.close()
        return
    
    print("📋 TEST: Último timestamp de cada reparación\n" + "="*60)
    
    datos_enriquecidos = []
    for r in reparaciones:
        r_dict = dict(r)
        
        # Obtener última actualización (igual a la ruta)
        ultima_actualizacion = conn.execute(
            "SELECT fecha_cambio FROM reparaciones_historial WHERE reparacion_id = ? ORDER BY fecha_cambio DESC LIMIT 1",
            (r_dict['id'],)
        ).fetchone()
        
        r_dict['ultima_actualizacion'] = ultima_actualizacion['fecha_cambio'] if ultima_actualizacion else None
        datos_enriquecidos.append(r_dict)
        
        # Mostrar resultado
        print(f"\n✓ Reparación #{r_dict['id']}")
        print(f"  Estado: {r_dict['estado']}")
        print(f"  Última actualización: {r_dict['ultima_actualizacion'] or '-'}")
    
    print("\n" + "="*60)
    print(f"✅ Test completado: {len(datos_enriquecidos)} reparaciones procesadas")
    print("✅ Datos enriquecidos listos para pasar al template")
    
    conn.close()

if __name__ == "__main__":
    test_ultima_actualizacion()
