#!/usr/bin/env python3
"""
Test: Verificar que el endpoint de pago público funciona con claves reales de Stripe
"""
import sys
import os
sys.path.insert(0, '.')
os.environ['STRIPE_SECRET_KEY'] = "sk_test_51T6eO5BLNTOC0gyI1zBErEGuZLtMVbzlGYQYb1Wl8EarLWaQZ4TEUXsjHFzhsS2iqE5TCrAKzMamynW4wV7AkC9K00DOQHNRr1"
os.environ['STRIPE_PUBLISHABLE_KEY'] = "pk_test_51T6eO5BLNTOC0gyIcEPQMP1VcfEtDQgOM7gyK61ajih7bt8qju1SfIca21YSYyl0LSmcNJnHhbCLaoVkCdWNvigx0055K1tjfq"

from app import app
from db import get_db
import json

print("\n✅ Test: Pago público con claves reales de Stripe\n")

# Crear/obtener una reparación de prueba
conn = get_db()
cursor = conn.cursor()
cursor.execute("SELECT id FROM clientes WHERE nombre = 'Juan Pérez' LIMIT 1")
row = cursor.fetchone()
customer_id = row['id'] if row else None

if not customer_id:
    cursor.execute(
        "INSERT INTO clientes (nombre, telefono, email, fecha_registro) VALUES (?, ?, ?, ?)",
        ('TestPaymentUser', '666123456', 'testpay@example.com', '2026-03-02')
    )
    conn.commit()
    customer_id = cursor.lastrowid

# Obtener email del cliente
cursor.execute("SELECT email FROM clientes WHERE id = ?", (customer_id,))
row = cursor.fetchone()
customer_email = row['email'] if row else 'testpay@example.com'

# Crear reparación
cursor.execute(
    "INSERT INTO reparaciones (cliente_id, dispositivo, descripcion, estado, fecha_entrada, precio, estado_pago) VALUES (?, ?, ?, ?, ?, ?, ?)",
    (customer_id, 'iPhone Test Payment', 'Test payment flow', 'Pendiente', '2026-03-02', 50.00, 'Pendiente')
)
conn.commit()
rep_id = cursor.lastrowid
conn.close()

print(f"1. Reparación creada: #{rep_id} (iPhone Test Payment, €50.00)")
print(f"   Cliente: TestPaymentUser ({customer_email})")

# Intentar crear sesión de pago
app.testing = True
with app.test_client() as client:
    # Obtener token CSRF del formulario de consulta
    resp = client.get('/consulta')
    import re
    csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.data.decode())
    csrf_token = csrf_match.group(1) if csrf_match else ''
    
    print(f"\n2. Token CSRF obtenido: {csrf_token[:20]}...")
    
    # POST a /publico/pagar/{id}
    print(f"\n3. Enviando solicitud de pago a POST /publico/pagar/{rep_id}...")
    resp = client.post(f'/publico/pagar/{rep_id}', data={
        'cliente_email': customer_email,
        'csrf_token': csrf_token
    }, follow_redirects=False)
    
    print(f"   Status Code: {resp.status_code}")
    location = resp.headers.get('Location', '')
    print(f"   Location: {location}")
    
    if 'checkout.stripe.com' in location or 'stripe' in location:
        print(f"   ✅ ÉXITO - Sesión Stripe creada")
        print(f"   Redirigiendo a Stripe checkout...")
        
    elif '/consulta' in location:
        print(f"   ❌ Redirige a /consulta (error en validación)")
        # Verificar el mensaje de error en siguiente click
        resp2 = client.get(location)
        html = resp2.data.decode()
        if 'Error' in html or 'error' in html:
            import re
            error_match = re.search(r'<div class="alert[^>]*>([^<]*Error[^<]*)<', html)
            if error_match:
                print(f"       Mensaje: {error_match.group(1).strip()[:200]}")
        
    elif resp.status_code in [200, 302]:
        # Posible error en formulario
        html = resp.data.decode()
        if 'Error de autenticación' in html:
            print(f"   ❌ Error: Error de autenticación")
        elif 'Error inesperado' in html:
            print(f"   ❌ Error: Error inesperado")
        else:
            print(f"   Revisando respuesta...")


print("\n" + "="*60)
print("✅ Test completado")
print("="*60 + "\n")
