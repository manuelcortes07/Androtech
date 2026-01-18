#!/usr/bin/env python
"""Script para probar la generación de PDFs con IVA"""

import urllib.request
import os
import time

# Esperar a que el servidor esté listo
time.sleep(3)

print("=" * 60)
print("PROBANDO GENERACIÓN DE PDFs CON IVA")
print("=" * 60)

try:
    # Descargar presupuesto
    print("\n[1/2] Descargando presupuesto...")
    urllib.request.urlretrieve(
        'http://localhost:5000/reparaciones/pdf/3?tipo=presupuesto',
        'test_presupuesto.pdf'
    )
    tamaño_p = os.path.getsize('test_presupuesto.pdf')
    print(f"     ✓ Presupuesto generado: {tamaño_p} bytes")
    
    # Descargar factura
    print("\n[2/2] Descargando factura...")
    urllib.request.urlretrieve(
        'http://localhost:5000/reparaciones/pdf/3?tipo=factura',
        'test_factura.pdf'
    )
    tamaño_f = os.path.getsize('test_factura.pdf')
    print(f"     ✓ Factura generada: {tamaño_f} bytes")
    
    print("\n" + "=" * 60)
    print("✅ ÉXITO: Ambos PDFs se generaron correctamente")
    print("=" * 60)
    print(f"\nArchivos creados:")
    print(f"  - test_presupuesto.pdf ({tamaño_p} bytes)")
    print(f"  - test_factura.pdf ({tamaño_f} bytes)")
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print("=" * 60)
