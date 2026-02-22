import sqlite3
from werkzeug.security import generate_password_hash
import pytest
import os

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


def test_login_and_consulta():
    reparacion_id = setup_test_user_and_data()

    client = app.app.test_client()

    # set csrf token in session
    with client.session_transaction() as sess:
        sess['csrf_token'] = 'testtoken'

    # Test login
    resp = client.post('/login', data={'usuario': 'testuser', 'contraseña': 'testpass', 'csrf_token': 'testtoken'})
    assert resp.status_code in (302, 303)

    # Test consulta (by id)
    with client.session_transaction() as sess:
        sess['csrf_token'] = 'testtoken'

    resp2 = client.post('/consulta', data={'id_reparacion': str(reparacion_id), 'csrf_token': 'testtoken'})
    assert resp2.status_code == 200
    content = resp2.get_data(as_text=True)
    assert 'Test Device' in content


if __name__ == '__main__':
    pytest.main(['-q', 'test_basic_routes.py'])
