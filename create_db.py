import sqlite3

conn = sqlite3.connect('database/andro.db')
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    telefono TEXT NOT NULL,
    email TEXT,
    fecha_registro TEXT
);
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reparaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER,
    descripcion TEXT NOT NULL,
    estado TEXT NOT NULL,
    fecha_inicio TEXT,
    fecha_fin TEXT,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);
""")

conn.commit()
conn.close()

print("Base de datos creada correctamente.")