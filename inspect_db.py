import sqlite3

conn = sqlite3.connect('database/andro_tech.db')
conn.row_factory = sqlite3.Row
users = conn.execute('SELECT id, usuario, rol, contraseña FROM usuarios').fetchall()
print('Usuarios:')
for u in users:
    print(dict(u))
conn.close()
