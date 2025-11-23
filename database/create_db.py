import sqlite3
import os

# Ruta correcta
db_path = "database/andro_tech.db"

# Crear carpeta si no existe
os.makedirs("database", exist_ok=True)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Tabla de clientes
cursor.execute("""
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    telefono TEXT,
    email TEXT,
    direccion TEXT
);
""")

# Tabla de reparaciones
cursor.execute("""
CREATE TABLE IF NOT EXISTS reparaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER,
    dispositivo TEXT NOT NULL,
    descripcion TEXT,
    estado TEXT DEFAULT 'Pendiente',
    fecha_entrada TEXT,
    fecha_salida TEXT,
    precio REAL,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);
""")

# Tabla usuarios (para login técnico)
cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL UNIQUE,
    contraseña TEXT NOT NULL,
    rol TEXT DEFAULT 'tecnico'
);
""")

conn.commit()
conn.close()

print("Base de datos creada correctamente ✔")
