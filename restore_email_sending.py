#!/usr/bin/env python3
"""
Script para restaurar el envío real de emails en AndroTech
Ejecutar después de configurar credenciales SMTP válidas
"""

import re

def restore_email_sending():
    """Restaurar el envío real de emails descomentando las líneas"""

    # Leer el archivo actual
    with open('utils/email_service.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Patrón para encontrar los bloques comentados de envío de email
    pattern = r'(\s+)# En producción, descomentar estas líneas:\s*\n(\s+)# # Crear mensaje.*?(\s+)# # Enviar email.*?(\s+)# self\.mail\.send\(msg\)'

    # Reemplazar con el código descomentado
    def replace_block(match):
        indent = match.group(1)
        return f'{indent}# Crear mensaje{chr(10)}{indent}msg = Message({chr(10)}{indent}    subject=f\'Payment Confirmed - Repair #{reparacion_id}\',{chr(10)}{indent}    recipients=[to_email],{chr(10)}{indent}    charset=\'utf-8\'{chr(10)}{indent}){chr(10)}{indent}msg.html = html_body{chr(10)}{indent}msg.content_type = \'text/html; charset=utf-8\'{chr(10)}{indent}# Enviar email{chr(10)}{indent}self.mail.send(msg)'

    # Aplicar el reemplazo
    new_content = re.sub(pattern, replace_block, content, flags=re.DOTALL)

    # También restaurar los otros métodos
    patterns = [
        (r'# En producción, descomentar estas líneas:\s*\n\s*# # Crear mensaje.*?subject=f\'Repair Status Update.*?\n.*?msg\.content_type = \'text/html; charset=utf-8\'\n\s*# # Enviar email\n\s*# self\.mail\.send\(msg\)', '            # Crear mensaje\n            msg = Message(\n                subject=f\'Repair Status Update #{reparacion_id} - {estado_nuevo}\',\n                recipients=[to_email],\n                charset=\'utf-8\'\n            )\n            msg.html = html_body\n            msg.content_type = \'text/html; charset=utf-8\'\n            # Enviar email\n            self.mail.send(msg)'),
        (r'# En producción, descomentar estas líneas:\s*\n\s*# # Crear mensaje.*?subject=f\'Factura.*?\n.*?msg\.content_type = \'text/html; charset=utf-8\'\n\s*# # Enviar email\n\s*# self\.mail\.send\(msg\)', '            # Crear mensaje\n            msg = Message(\n                subject=f\'Factura - Reparacion #{reparacion_id}\',\n                recipients=[to_email],\n                charset=\'utf-8\'\n            )\n            msg.html = html_body\n            msg.content_type = \'text/html; charset=utf-8\'\n            # Enviar email\n            self.mail.send(msg)')
    ]

    for pattern, replacement in patterns:
        new_content = re.sub(pattern, replacement, new_content, flags=re.DOTALL)

    # Remover los prints de debug y las líneas de prueba
    new_content = re.sub(r'\s*# Para pruebas: imprimir en consola.*?\n.*?=====================================\n', '', new_content, flags=re.DOTALL)
    new_content = re.sub(r'\s*print\("=== EMAIL DE PRUEBA.*?\n', '', new_content, flags=re.MULTILINE)
    new_content = re.sub(r'\s*print\(f"Para: \{to_email\}"\)\n', '', new_content, flags=re.MULTILINE)
    new_content = re.sub(r'\s*print\(f"Asunto: .*?"\)\n', '', new_content, flags=re.MULTILINE)
    new_content = re.sub(r'\s*print\(f"Contenido: .*?"\)\n', '', new_content, flags=re.MULTILINE)
    new_content = re.sub(r'\s*print\("====================================="\)\n', '', new_content, flags=re.MULTILINE)

    # Escribir el archivo modificado
    with open('utils/email_service.py', 'w', encoding='utf-8') as f:
        f.write(new_content)

    print("✅ Sistema de email restaurado para envío real")
    print("Recuerda configurar credenciales SMTP válidas en .env")

if __name__ == '__main__':
    print("🔄 Restaurando envío real de emails...")
    restore_email_sending()
    print("🎉 ¡Listo! El sistema ahora enviará emails reales.")