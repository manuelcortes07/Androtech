# Sistema de Email Automático - AndroTech

## 📧 Descripción

El sistema de email automático de AndroTech envía notificaciones por email a los clientes cuando:
- Se confirma un pago exitosamente
- Cambia el estado de una reparación
- Se envían facturas

## 🚀 Configuración

### 1. Variables de Entorno

Configura las siguientes variables de entorno:

```bash
# Configuración SMTP
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USE_SSL=false
MAIL_USERNAME=tu-email@gmail.com
MAIL_PASSWORD=tu-contraseña
MAIL_DEFAULT_SENDER=noreply@androtech.com
```

### 2. Configuración Rápida

Ejecuta el script de configuración automática:

```powershell
.\configure_email.ps1
```

Este script te guiará para configurar todas las variables necesarias.

### 3. Configuración para Gmail

Para usar Gmail como servidor SMTP:

1. **Habilitar acceso de aplicaciones menos seguras** (no recomendado):
   - Ve a [Configuración de Google](https://myaccount.google.com/security)
   - Activa "Acceso de aplicaciones menos seguras"

2. **Usar contraseña de aplicación** (recomendado si tienes 2FA):
   - Ve a [Contraseñas de aplicación](https://myaccount.google.com/apppasswords)
   - Genera una contraseña específica para la aplicación
   - Usa esta contraseña en `MAIL_PASSWORD`

## 📧 Plantillas de Email

Las plantillas HTML se encuentran en `templates/emails/`:

- `payment_confirmation.html` - Confirmación de pago
- `repair_status_update.html` - Actualización de estado de reparación

## 🔧 Funcionalidades

### Email de Confirmación de Pago
- Se envía automáticamente cuando un webhook de Stripe confirma el pago
- Incluye detalles del pago, reparación y próximos pasos

### Email de Actualización de Estado
- Se envía cuando cambia el estado de una reparación
- Incluye estado anterior/nuevo y detalles de la reparación
- Mensajes específicos según el estado (Terminado, Entregado, etc.)

### Email de Factura
- Función disponible para envío de facturas
- Usa la misma plantilla que la confirmación de pago

## 📊 Eventos que Disparan Emails

1. **Pago confirmado** → `email_service.send_payment_confirmation()`
2. **Estado de reparación actualizado** → `email_service.send_repair_status_update()`
3. **Factura enviada** → `email_service.send_invoice()`

## 🐛 Solución de Problemas

### Error de autenticación SMTP
- Verifica que `MAIL_USERNAME` y `MAIL_PASSWORD` sean correctos
- Para Gmail, usa una "contraseña de aplicación" si tienes 2FA
- Asegúrate de que el puerto (587) y TLS estén configurados correctamente

### Emails no se envían
- Verifica que todas las variables de entorno estén configuradas
- Revisa los logs de la aplicación para errores de email
- Confirma que el cliente tenga un email válido registrado

### Plantillas no se cargan
- Asegúrate de que los archivos `.html` estén en `templates/emails/`
- Verifica que Flask pueda acceder a la carpeta de templates

## 📝 Logs

Los eventos de email se registran en los logs de la aplicación:
- Envío exitoso: `[EMAIL] 📧 Email de confirmación enviado a user@example.com`
- Error: `Error enviando email de confirmación: [detalles del error]`

## 🔒 Seguridad

- Las contraseñas SMTP se almacenan como variables de entorno
- No se incluyen en el código fuente
- Se recomienda usar contraseñas de aplicación en lugar de contraseñas principales

## 🎯 Próximos Pasos

1. Configurar las variables de entorno
2. Probar con una reparación de prueba
3. Personalizar las plantillas HTML según la identidad de marca
4. Agregar más tipos de notificaciones según necesidades