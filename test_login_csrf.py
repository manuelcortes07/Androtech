#!/usr/bin/env python3
"""
Test: Login con CSRF token extraído del formulario
"""
import sys
import re
sys.path.insert(0, '.')

from app import app

client = app.test_client()

print("\n🔐 Test: Login con CSRF token\n")

with client:
    # 1. Obtener página de login para extraer CSRF token
    print("1️⃣  Obteniendo formulario de login...")
    response = client.get('/login')
    
    if response.status_code != 200:
        print(f"   ❌ GET /login falló: {response.status_code}")
        sys.exit(1)
    
    # Extraer CSRF token del HTML
    html = response.data.decode()
    csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    
    if not csrf_match:
        print("   ⚠️  No se encontró CSRF token en el formulario")
        csrf_token = None
    else:
        csrf_token = csrf_match.group(1)
        print(f"   ✅ CSRF token extraído: {csrf_token[:20]}...")
    
    # 2. Intentar login con CSRF token
    print("\n2️⃣  Intentando login con CSRF token...")
    data = {
        'usuario': 'admin',
        'contraseña': 'admin123',
    }
    if csrf_token:
        data['csrf_token'] = csrf_token
    
    response = client.post('/login', data=data)
    
    print(f"   POST /login Status: {response.status_code}")
    location = response.headers.get('Location')
    print(f"   Location: {location}")
    
    # Si fue redirect, verificar si fue a dashboard o a login
    if response.status_code == 302:
        if 'dashboard' in location:
            print("   ✅ ¡Redirect a DASHBOARD!")
        elif 'login' in location:
            print("   ❌ Redirect a LOGIN (auth failed)")
    
    # 3. Verificar sesión
    print("\n3️⃣  Verificando sesión...")
    from flask import session
    print(f"   session.get('usuario'): {session.get('usuario')}")
    print(f"   session.get('rol'): {session.get('rol')}")
    
    # 4. Acceder a dashboard
    if session.get('usuario'):
        print("\n4️⃣  Accediendo a dashboard...")
        response = client.get('/dashboard')
        print(f"   GET /dashboard Status: {response.status_code}")
        if response.status_code == 200:
            print("   ✅ ¡Dashboard accesible!")
            # Buscar la sección de auditoría
            if 'Auditoría Reciente' in response.data.decode():
                print("   ✅ ¡Sección de auditoría visible!")
            else:
                print("   ❌ Sección de auditoría NO visible")
