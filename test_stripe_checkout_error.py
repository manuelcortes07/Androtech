#!/usr/bin/env python3
"""Test para verificar manejo de errores de autenticación al crear sesión Stripe.

Se configura una clave secreta incorrecta y se simula que
stripe.checkout.Session.create lanza AuthenticationError. Debería
redirigirse al usuario con un "flash" adecuado.
"""
import sys
import os
sys.path.insert(0, '.')

# preparar entorno antes de importar app (app lee variables al import)
os.environ['STRIPE_SECRET_KEY'] = 'pk_test_invalid'  # intencionadamente errónea

from app import app
from db import get_db
import stripe


def setup_reparacion():
    """Asegura que haya una reparación con precio válido y email."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM reparaciones WHERE dispositivo = ? LIMIT 1", ('AUTH_ERR_TEST',))
    row = cursor.fetchone()
    if row:
        rep_id = row['id'] if hasattr(row, 'keys') else row[0]
    else:
        cursor.execute(
            "INSERT INTO reparaciones (cliente_id, dispositivo, descripcion, estado, fecha_entrada, precio, estado_pago, cliente_email) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (None, 'AUTH_ERR_TEST', 'Prueba auth error', 'Pendiente', '2026-03-01', 10.00, 'Pendiente', 'cliente@example.com')
        )
        conn.commit()
        rep_id = cursor.lastrowid
    conn.close()
    return rep_id


def test_checkout_auth_error(monkeypatch):
    rep_id = setup_reparacion()

    # asegurarnos de que stripe.api_key coincide con env (valor inválido)
    stripe.api_key = os.environ['STRIPE_SECRET_KEY']

    # parchear la creación de sesión para forzar AuthenticationError
    def fake_create(*args, **kwargs):
        raise stripe.error.AuthenticationError("Invalid API Key provided")

    monkeypatch.setattr(stripe.checkout.Session, 'create', fake_create)

    app.testing = True
    with app.test_client() as client:
        # preparar token CSRF manualmente
        with client.session_transaction() as sess:
            sess['csrf_token'] = 'tokentest'

        resp = client.post(f'/publico/pagar/{rep_id}', data={
            'cliente_email': 'cliente@example.com',
            'csrf_token': 'tokentest'
        }, follow_redirects=True)

        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Error de autenticación con Stripe' in html
        assert 'Clave secreta de Stripe inválida' not in html  # nuestra validación no se ejecuta antes

        # también podemos verificar que el estado de pago sigue pendiente
        conn = get_db()
        row = conn.execute('SELECT estado_pago FROM reparaciones WHERE id = ?', (rep_id,)).fetchone()
        conn.close()
        assert row and row['estado_pago'] == 'Pendiente'
