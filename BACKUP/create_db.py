import sqlite3

# Ruta a la base de datos
db_path = "database/andro.db"

# Conexión
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# TABLA: clientes
cursor.execute("""
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    telefono TEXT NOT NULL,
    email TEXT,
    fecha_registro TEXT NOT NULL
);
""")

# TABLA: reparaciones
cursor.execute("""
CREATE TABLE IF NOT EXISTS reparaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    dispositivo TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    estado TEXT NOT NULL,
    fecha_entrada TEXT NOT NULL,
    fecha_salida TEXT,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);
""")

conn.commit()
conn.close()

print("Base de datos creada correctamente.")
