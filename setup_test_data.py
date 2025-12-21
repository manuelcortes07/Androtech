import sqlite3

conn = sqlite3.connect('database/andro_tech.db')
cursor = conn.cursor()

# Create a test client
cursor.execute('''
    INSERT OR IGNORE INTO clientes (id, nombre, telefono, email)
    VALUES (1, 'Cliente Prueba', '123456789', 'test@example.com')
''')

# Update test repairs to use existing client IDs
cursor.execute('UPDATE reparaciones SET cliente_id = 1 WHERE cliente_id NOT IN (SELECT id FROM clientes)')

conn.commit()

# Verify the data
cursor.execute('''
    SELECT c.nombre, c.telefono, r.dispositivo, r.estado
    FROM clientes c
    JOIN reparaciones r ON c.id = r.cliente_id
    WHERE c.telefono = '123456789'
''')
results = cursor.fetchall()
print('Test client repairs:')
for result in results:
    print(f'  Client: {result[0]}, Phone: {result[1]}, Device: {result[2]}, Status: {result[3]}')

conn.close()
print('✅ Test data setup completed')