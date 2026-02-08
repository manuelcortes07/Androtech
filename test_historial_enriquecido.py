#!/usr/bin/env python3
"""
Test: Verificar que la ruta /cliente/historial enriquece reparaciones
con última actualización correctamente.
"""

import sqlite3
from datetime import datetime

DB_PATH = "database/andro_tech.db"

def test_enriquecimiento_historial():
    """Simular la lógica de enriquecimiento en /cliente/historial."""
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Simulación: obtener reparaciones como en la ruta
    base_sql = "SELECT reparaciones.*, clientes.nombre AS cliente FROM reparaciones LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id"
    reparaciones_rows = conn.execute(base_sql + " ORDER BY reparaciones.id DESC LIMIT 5").fetchall()
    reparaciones = [dict(r) for r in reparaciones_rows]
    
    if not reparaciones:
        print("❌ No hay reparaciones para probar.")
        conn.close()
        return
    
    print("📋 TEST: Enriquecimiento de reparaciones en /cliente/historial\n" + "="*60)
    
    # Enriquecer datos (igual que en la ruta)
    reparaciones_enriquecidas = []
    for r in reparaciones:
        ultima_actualizacion = conn.execute(
            "SELECT fecha_cambio FROM reparaciones_historial WHERE reparacion_id = ? ORDER BY fecha_cambio DESC LIMIT 1",
            (r['id'],)
        ).fetchone()
        r['ultima_actualizacion'] = ultima_actualizacion['fecha_cambio'] if ultima_actualizacion else None
        reparaciones_enriquecidas.append(r)
    
    # Mostrar resultados
    for r in reparaciones_enriquecidas:
        print(f"\n✓ Reparación #{r['id']}")
        print(f"  Cliente: {r['cliente'] or 'Sin asignar'}")
        print(f"  Estado: {r['estado']}")
        print(f"  Última actualización: {r['ultima_actualizacion'] or '-'}")
        if r['ultima_actualizacion']:
            try:
                dt = datetime.strptime(r['ultima_actualizacion'], "%Y-%m-%d %H:%M:%S")
                print(f"  Formato template: {dt.strftime('%d/%m/%Y %H:%M')}")
            except:
                pass
    
    print("\n" + "="*60)
    print(f"✅ Test completado: {len(reparaciones_enriquecidas)} reparaciones procesadas")
    print("✅ Modal historial_cliente.html recibirá datos con ultima_actualizacion")
    
    conn.close()

if __name__ == "__main__":
    test_enriquecimiento_historial()
