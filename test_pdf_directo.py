#!/usr/bin/env python
"""Script para probar la función de generación de PDF directamente"""

from utils.pdf_generator import generar_presupuesto_pdf

# Datos de prueba
reparacion_data = {
    'id': 3,
    'dispositivo': 'iPhone 14 Pro',
    'estado': 'Reparado',
    'fecha_entrada': '2026-01-15',
    'precio': 150.00,
    'descripcion': 'Cambio de pantalla y batería',
    'cliente_nombre': 'Juan González',
    'cliente_telefono': '+34 666 123 456',
}

print("=" * 60)
print("PRUEBA DE FUNCIÓN generar_presupuesto_pdf()")
print("=" * 60)

try:
    # Generar presupuesto
    print("\n[1/2] Generando presupuesto...")
    pdf_presupuesto = generar_presupuesto_pdf(reparacion_data, tipo_documento="presupuesto")
    tamaño_p = len(pdf_presupuesto.getvalue())
    print(f"     ✓ Presupuesto generado: {tamaño_p} bytes")
    
    # Guardar archivo
    with open('test_presupuesto_directo.pdf', 'wb') as f:
        f.write(pdf_presupuesto.getvalue())
    print(f"     ✓ Guardado en: test_presupuesto_directo.pdf")
    
    # Generar factura
    print("\n[2/2] Generando factura...")
    pdf_factura = generar_presupuesto_pdf(reparacion_data, tipo_documento="factura")
    tamaño_f = len(pdf_factura.getvalue())
    print(f"     ✓ Factura generada: {tamaño_f} bytes")
    
    # Guardar archivo
    with open('test_factura_directo.pdf', 'wb') as f:
        f.write(pdf_factura.getvalue())
    print(f"     ✓ Guardado en: test_factura_directo.pdf")
    
    print("\n" + "=" * 60)
    print("✅ ÉXITO: Ambos PDFs se generaron correctamente")
    print("=" * 60)
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    print("=" * 60)
