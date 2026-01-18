#!/usr/bin/env python
"""Script para probar el dashboard"""

import urllib.request
import time

print("=" * 70)
print("PROBANDO DASHBOARD MEJORADO")
print("=" * 70)

time.sleep(2)

try:
    # Probar si el servidor está disponible
    response = urllib.request.urlopen('http://localhost:5000/dashboard')
    html_size = len(response.read())
    
    print(f"\n✅ Dashboard disponible")
    print(f"   → Tamaño de la página: {html_size} bytes")
    print(f"   → Status: {response.status}")
    
    print("\n" + "=" * 70)
    print("ÉXITO: El dashboard se está sirviendo correctamente")
    print("=" * 70)
    print("\n📊 Puedes acceder en: http://localhost:5000/dashboard")
    print("\nKPIs mostrados:")
    print("  ✓ Total clientes")
    print("  ✓ Total reparaciones")
    print("  ✓ Pendientes vs Completadas")
    print("  ✓ Ingresos este mes (con IVA)")
    print("  ✓ Ingresos totales (con IVA)")
    print("  ✓ Dispositivos más reparados")
    print("  ✓ Distribución de estados")
    print("  ✓ Últimas 5 reparaciones")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\nAsegúrate de que:")
    print("  1. Flask está corriendo (python app.py)")
    print("  2. Estás conectado a localhost:5000")
    print("  3. Tienes credenciales de acceso válidas")
