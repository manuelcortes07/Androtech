#!/usr/bin/env python3
"""
Test básico: Simula webhook de Stripe para comprobar actualización de DB
"""
import sys
sys.path.insert(0, '.')
import os
# Ensure webhook secret is set before importing app (app reads env at import)
os.environ['STRIPE_WEBHOOK_SECRET'] = 'whsec_test'

from app import app
from db import get_db
import json
import os

print('\n🔁 Test: Webhook de Stripe simulado (pago)')

# Crear una reparación de prueba si no existe
conn = get_db()
cursor = conn.cursor()
cursor.execute("SELECT id FROM reparaciones WHERE dispositivo = ? LIMIT 1", ('WEBHOOK_TEST_DEVICE',))
row = cursor.fetchone()
if row:
    reparacion_id = row['id'] if hasattr(row, 'keys') else row[0]
else:
    cursor.execute(
        "INSERT INTO reparaciones (cliente_id, dispositivo, descripcion, estado, fecha_entrada, precio, estado_pago) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (NULL_PLACEHOLDER := None, 'WEBHOOK_TEST_DEVICE', 'Prueba webhook', 'Pendiente', '2026-02-23', 25.00, 'Pendiente')
    )
    conn.commit()
    reparacion_id = cursor.lastrowid

conn.close()

# Construir evento simulado
fake_event = {
    'type': 'checkout.session.completed',
    'data': {
        'object': {
            'id': 'cs_test_123',
            'payment_status': 'paid',
            'amount_total': 2500,  # centavos -> 25.00
            'metadata': {
                'reparacion_id': str(reparacion_id),
                'cliente_email': 'cliente@test.local'
            }
        }
    }
}

# Monkeypatch stripe.Webhook.construct_event to return fake_event
try:
    import stripe
except Exception:
    # Crear un stub mínimo si la librería no está instalada (para tests locales)
    import types
    stripe = types.SimpleNamespace()
    class _Webhook:
        @staticmethod
        def construct_event(payload, sig_header, secret):
            raise RuntimeError('stripe not installed')
    stripe.Webhook = _Webhook

original_construct_event = None
if hasattr(stripe, 'Webhook') and hasattr(stripe.Webhook, 'construct_event'):
    original_construct_event = stripe.Webhook.construct_event
    stripe.Webhook.construct_event = lambda payload, sig_header, secret: fake_event

with app.test_client() as client:
    headers = {
        'Content-Type': 'application/json',
        'Stripe-Signature': 't=123456'  # valor cualquiera, estamos parcheando la verificación
    }
    # Ensure webhook secret is set for the test to bypass configuration check
    os.environ['STRIPE_WEBHOOK_SECRET'] = 'whsec_test'
    resp = client.post('/stripe/webhook', data=json.dumps(fake_event), headers=headers)
    print('Status:', resp.status_code)
    print('Response:', resp.data.decode())

# Verificar DB
conn = get_db()
row = conn.execute('SELECT estado_pago, fecha_pago, metodo_pago FROM reparaciones WHERE id = ?', (reparacion_id,)).fetchone()
print('DB after webhook:', dict(row) if row else None)
conn.close()

# Restore original
if original_construct_event:
    stripe.Webhook.construct_event = original_construct_event

print('\n✅ Test webhook finalizado')
