import sqlite3
from werkzeug.security import generate_password_hash
import os
import sys

import app

DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'andro_tech.db')


def setup_test_user_and_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Create test user
    password = generate_password_hash('testpass')
    cur.execute("INSERT OR REPLACE INTO usuarios (usuario, contraseña, rol) VALUES (?, ?, ?)",
                ('testuser', password, 'admin'))

    # Create test client
    cur.execute("INSERT OR REPLACE INTO clientes (id, nombre, telefono, email) VALUES (?, ?, ?, ?)",
                (9999, 'Test Cliente', '999000111', 'testclient@example.com'))

    # Create test repair
    cur.execute("INSERT INTO reparaciones (cliente_id, dispositivo, descripcion, estado, fecha_entrada, precio) VALUES (?, ?, ?, ?, ?, ?)",
                (9999, 'Test Device', 'Descripcion', 'Pendiente', '2026-02-22', 50.0))
    reparacion_id = cur.lastrowid

    conn.commit()
    conn.close()
    return reparacion_id


def main():
    print('Setting up test data...')
    reparacion_id = setup_test_user_and_data()

    client = app.app.test_client()

    # set csrf token in session
    with client.session_transaction() as sess:
        sess['csrf_token'] = 'testtoken'

    # Test login
    resp = client.post('/login', data={'usuario': 'testuser', 'contraseña': 'testpass', 'csrf_token': 'testtoken'})
    if resp.status_code in (302, 303):
        print('LOGIN OK')
    else:
        print('LOGIN FAILED', resp.status_code)
        sys.exit(1)

    # Test consulta (by id)
    with client.session_transaction() as sess:
        sess['csrf_token'] = 'testtoken'

    resp2 = client.post('/consulta', data={'id_reparacion': str(reparacion_id), 'csrf_token': 'testtoken'})
    if resp2.status_code != 200:
        print('CONSULTA FAILED', resp2.status_code)
        sys.exit(1)

    content = resp2.get_data(as_text=True)
    if 'Test Device' in content:
        print('CONSULTA OK')
    else:
        print('CONSULTA MISSING CONTENT')
        sys.exit(1)

    print('ALL BASIC TESTS PASSED')

if __name__ == '__main__':
    main()
