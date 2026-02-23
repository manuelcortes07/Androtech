from db import get_db

conn = get_db()
c = conn.cursor()
result = c.execute('SELECT usuario, contraseña FROM usuarios WHERE usuario = "admin"').fetchone()
print(f"Admin user: {result[0]}")
print(f"Password hash starts with: {result[1][:20]}")
conn.close()
