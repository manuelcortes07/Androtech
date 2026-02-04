#!/usr/bin/env python3
"""Verificar que la migración fue exitosa."""

import sqlite3

DB_PATH = "database/andro_tech.db"
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Verificar tabla existe
cursor.execute("""
    SELECT name FROM sqlite_master 
    WHERE type='table' AND name='reparaciones_historial'
""")
table_exists = cursor.fetchone()

if table_exists:
    print("✅ Tabla reparaciones_historial existe correctamente.")
    
    # Ver estructura
    cursor.execute("PRAGMA table_info(reparaciones_historial)")
    columns = cursor.fetchall()
    print("\n   Columnas:")
    for col in columns:
        print(f"   - {col[1]} ({col[2]})")
    
    # Ver índices
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND tbl_name='reparaciones_historial'
    """)
    indexes = cursor.fetchall()
    print("\n   Índices:")
    for idx in indexes:
        print(f"   - {idx[0]}")
    
    # Contar registros de historial
    cursor.execute("SELECT COUNT(*) FROM reparaciones_historial")
    count = cursor.fetchone()[0]
    print(f"\n   Registros de historial: {count}")
else:
    print("❌ Tabla reparaciones_historial NO existe.")

conn.close()
