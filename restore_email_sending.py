#!/usr/bin/env python3
"""
Script para restaurar el envío real de emails en AndroTech
Ejecutar después de configurar credenciales SMTP válidas
"""

def restore_email_sending():
    """Restaurar el envío real de emails descomentando las líneas"""

    # Leer el archivo actual
    with open('utils/email_service.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Reemplazos simples para descomentar el código
    replacements = [
        # Para send_payment_confirmation
        ('# Para pruebas: imprimir en consola en lugar de enviar', '# Crear mensaje'),
        ('print("=== EMAIL DE PRUEBA - NO SE ENVÍA ===")', 'msg = Message('),
        ('print(f"Para: {to_email}")', '    subject=\'Payment Confirmed - Repair\','),
        ('print(f"Asunto: Payment Confirmed - Repair")', '    recipients=[to_email],'),
        ('print(f"Contenido: {html_body[:200]}...")', '    charset=\'utf-8\''),
        ('print("=====================================")', ')'),
        ('', 'msg.html = html_body'),
        ('', 'msg.content_type = \'text/html; charset=utf-8\''),
        ('', '# Enviar email'),
        ('', 'self.mail.send(msg)'),

        # Para send_repair_status_update
        ('# Para pruebas: imprimir en consola en lugar de enviar', '# Crear mensaje'),
        ('print("=== EMAIL DE PRUEBA - NO SE ENVÍA ===")', 'msg = Message('),
        ('print(f"Para: {to_email}")', '    subject=f\'Repair Status Update #{reparacion_id} - {estado_nuevo}\','),
        ('print(f"Asunto: Repair Status Update #{reparacion_id} - {estado_nuevo}")', '    recipients=[to_email],'),
        ('print(f"Contenido: {html_body[:200]}...")', '    charset=\'utf-8\''),
        ('print("=====================================")', ')'),
        ('', 'msg.html = html_body'),
        ('', 'msg.content_type = \'text/html; charset=utf-8\''),
        ('', '# Enviar email'),
        ('', 'self.mail.send(msg)'),

        # Para send_invoice
        ('# Para pruebas: imprimir en consola en lugar de enviar', '# Crear mensaje'),
        ('print("=== EMAIL DE PRUEBA - NO SE ENVÍA ===")', 'msg = Message('),
        ('print(f"Para: {to_email}")', '    subject=f\'Factura - Reparacion #{reparacion_id}\','),
        ('print(f"Asunto: Factura - Reparacion #{reparacion_id}")', '    recipients=[to_email],'),
        ('print(f"Contenido: {html_body[:200]}...")', '    charset=\'utf-8\''),
        ('print("=====================================")', ')'),
        ('', 'msg.html = html_body'),
        ('', 'msg.content_type = \'text/html; charset=utf-8\''),
        ('', '# Enviar email'),
        ('', 'self.mail.send(msg)'),
    ]

    # Aplicar reemplazos
    for old, new in replacements:
        if old and new:
            content = content.replace(old, new)

    # Escribir el archivo modificado
    with open('utils/email_service.py', 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ Sistema de email restaurado para envío real")
    print("Recuerda configurar credenciales SMTP válidas en .env")

if __name__ == '__main__':
    print("🔄 Restaurando envío real de emails...")
    restore_email_sending()
    print("🎉 ¡Listo! El sistema ahora enviará emails reales.")