#!/usr/bin/env python3
"""
Migración DB: Crear tabla reparaciones_historial para auditoría de cambios de estado.

Descripción:
    - Crea tabla reparaciones_historial (sin romper datos existentes)
    - Tabla es reversible: puede eliminarse sin afectar datos en reparaciones
    - Registra: reparacion_id, estado_anterior, estado_nuevo, fecha_cambio (ISO timestamp)

Uso:
    python migrate_historial.py       # Crear (idempotente)
    python migrate_historial.py --revert  # Eliminar tabla (CUIDADO: pierde historial)
"""

import sqlite3
import sys

DB_PATH = "database/andro_tech.db"

def create_historial_table():
    """Crear tabla reparaciones_historial si no existe (idempotente)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reparaciones_historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reparacion_id INTEGER NOT NULL,
                estado_anterior TEXT,
                estado_nuevo TEXT NOT NULL,
                fecha_cambio TEXT NOT NULL,
                usuario TEXT,
                FOREIGN KEY (reparacion_id) REFERENCES reparaciones(id)
            );
        """)
        
        # Índice para búsquedas rápidas por reparacion_id y fecha
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_historial_reparacion 
            ON reparaciones_historial(reparacion_id, fecha_cambio DESC);
        """)
        
        conn.commit()
        print("✅ Tabla reparaciones_historial creada correctamente.")
        print("   - Almacena historial de cambios de estado")
        print("   - Índices creados para rendimiento")
        
    except Exception as e:
        print(f"❌ Error creando tabla: {e}")
        return False
    finally:
        conn.close()
    
    return True


def revert_historial_table():
    """Eliminar tabla reparaciones_historial (irreversible)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Primero eliminar índice
        cursor.execute("DROP INDEX IF EXISTS idx_historial_reparacion;")
        # Luego tabla
        cursor.execute("DROP TABLE IF EXISTS reparaciones_historial;")
        
        conn.commit()
        print("⚠️  Tabla reparaciones_historial eliminada.")
        print("   ADVERTENCIA: El historial de cambios se ha perdido.")
        
    except Exception as e:
        print(f"❌ Error revertiendo: {e}")
        return False
    finally:
        conn.close()
    
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--revert":
        confirm = input("⚠️  ¿Seguro que deseas ELIMINAR la tabla reparaciones_historial? (s/n): ")
        if confirm.lower() == 's':
            revert_historial_table()
        else:
            print("Cancelado.")
    else:
        create_historial_table()
