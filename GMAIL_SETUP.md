# Configuración de Gmail para AndroTech

## 🎯 Opciones para Gmail

Gmail ofrece varias formas de configurar SMTP, dependiendo de tu configuración de seguridad:

### Opción 1: Contraseña de Aplicación (Recomendado - Seguro)

**Ventajas:**
- ✅ Funciona con 2FA activado
- ✅ Más seguro que contraseña normal
- ✅ Google lo recomienda

**Configuración:**

1. **Activar Verificación en 2 pasos:**
   - Ve a https://myaccount.google.com/security
   - En "Verificación en 2 pasos", haz clic en "Comenzar"
   - Sigue los pasos para activarlo

2. **Generar Contraseña de Aplicación:**
   - Ve a https://myaccount.google.com/security
   - En "Contraseñas de aplicaciones", haz clic en "Contraseñas de aplicaciones"
   - Selecciona "Correo" y "Otro (nombre personalizado)"
   - Ingresa "AndroTech" como nombre
   - Copia la contraseña de 16 caracteres generada

3. **Configurar en .env:**
   ```env
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USE_TLS=true
   MAIL_USE_SSL=false
   MAIL_USERNAME=tu-email@gmail.com
   MAIL_PASSWORD=abcd-efgh-ijkl-mnop  # La contraseña de aplicación
   MAIL_DEFAULT_SENDER=noreply@androtech.com
   ```

### Opción 2: Contraseña Normal (Solo si no tienes 2FA)

**⚠️ No recomendado por Google, pero funciona si:**
- No tienes 2FA activado
- Tu cuenta es antigua y Google aún lo permite

```env
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USE_SSL=false
MAIL_USERNAME=tu-email@gmail.com
MAIL_PASSWORD=tu-contraseña-normal
MAIL_DEFAULT_SENDER=noreply@androtech.com
```

## 🔧 Solución de Problemas

### Error 535: Authentication Failed
```
Posibles causas:
1. Contraseña incorrecta
2. No usaste contraseña de aplicación (con 2FA)
3. La cuenta tiene restricciones de seguridad
4. Gmail bloqueó el acceso por "actividad sospechosa"
```

**Soluciones:**
- Verifica que uses la contraseña de aplicación correcta
- Revisa que no haya espacios extra en la contraseña
- Intenta generar una nueva contraseña de aplicación

### Error 534: Application-specific password required
```
Significa que tienes 2FA activado pero usaste la contraseña normal.
Solución: Genera y usa una contraseña de aplicación.
```

### Error 454: Temporary authentication failure
```
Usualmente temporal. Espera unos minutos y vuelve a intentar.
Si persiste, revisa la configuración de seguridad de tu cuenta.
```

## 🧪 Probar Configuración

### Prueba Específica de Gmail
```bash
python test_gmail.py
```

### Prueba General
```bash
python test_email_console.py
```

### Alternar Configuraciones
```bash
python switch_email_config.py
```

## 📊 Comparación: Gmail vs Outlook

| Aspecto | Gmail | Outlook |
|---------|-------|---------|
| **Seguridad** | Requiere 2FA + contraseña app | Contraseña normal |
| **Facilidad** | Más pasos de configuración | Más simple |
| **Fiabilidad** | Muy buena | Excelente |
| **Límites** | 500 emails/día gratis | 300 emails/día |
| **Soporte** | Bueno | Excelente |

## 🎯 Recomendación

- **Para principiantes:** Usa Outlook (más fácil de configurar)
- **Si prefieres Gmail:** Configura contraseña de aplicación
- **Para producción:** Considera servicios como SendGrid o Mailgun (más profesional)

## 📞 Soporte

Si tienes problemas con Gmail:
1. Revisa que la contraseña de aplicación sea correcta
2. Verifica que no haya espacios en la configuración
3. Prueba con `python test_gmail.py`
4. Si no funciona, considera usar Outlook como alternativa