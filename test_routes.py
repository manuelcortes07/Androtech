#!/usr/bin/env python3
"""
Test: Verificar rutas básicas
"""
import sys
sys.path.insert(0, '.')

from app import app

client = app.test_client()

print("\n🔍 Prueba de rutas básicas\n")

# Test 1: Index sin sesión
print("1️⃣  GET / sin sesión...")
response = client.get('/')
print(f"   Status: {response.status_code}")

# Test 2: Login GET
print("\n2️⃣  GET /login...")
response = client.get('/login')
print(f"   Status: {response.status_code}")
print(f"   'login.html' en response: {'login.html' in response.data.decode()}")

# Test 3: Login POST
print("\n3️⃣  POST /login (admin/admin123)...")
response = client.post('/login', data={
    'usuario': 'admin',
    'contraseña': 'admin123'
})
print(f"   Status: {response.status_code}")
print(f"   Location header: {response.headers.get('Location')}")

# Test 4: Usar sesión
print("\n4️⃣  Usando sesión persistente...")
with client:
    # Login
    print("   POST /login...")
    response = client.post('/login', data={
        'usuario': 'admin',
        'contraseña': 'admin123'
    })
    print(f"      Status: {response.status_code}")
    
    # Seguir redirección
    if response.status_code == 302:
        location = response.headers.get('Location')
        print(f"      Redirect a: {location}")
        response = client.get(location)
        print(f"      GET {location} status: {response.status_code}")
    
    # Ahora acceder a dashboard
    print("   GET /dashboard...")
    response = client.get('/dashboard')
    print(f"      Status: {response.status_code}")
    if response.status_code == 302:
        print(f"      ¡Redirige a: {response.headers.get('Location')}")
    else:
        print(f"      ✅ Response OK")
        print(f"      'dashboard' en response: {'dashboard' in response.data.decode()}")
