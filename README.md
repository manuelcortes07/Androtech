# AndroTech - Gestión de Reparaciones con Pagos Públicos

Aplicación Flask para gestionar reparaciones de dispositivos móviles con sistema de pagos público integrado mediante Stripe Checkout.

## 🚀 Características Principales

- **Dashboard administrativo** con KPIs de reparaciones y pagos
- **Consulta pública**: clientes pueden ver estado de reparaciones sin login
- **Pagos públicos con Stripe**: clientes pagan directamente desde la web con tarjeta
- **Sistema de email automático**: notificaciones de pagos y actualizaciones de reparaciones
- **Generación de PDFs**: presupuestos y facturas automáticas
- **Filtros avanzados**: búsqueda por cliente, estado, fechas y rango de precio
- **Historial de pagos**: registro de transacciones y métodos de pago
- **Autenticación segura**: contraseñas hasheadas con werkzeug

## 📋 Requisitos

- Python 3.8+
- pip (gestor de paquetes Python)
- Git (opcional, para clonar el repositorio)
- Stripe CLI (opcional, para probar webhooks localmente)

## 💻 Instalación Rápida (Windows)

### Opción A: Automática con script

```powershell
# 1. Abre PowerShell en la carpeta del proyecto
# 2. Ejecuta el script de setup
.\setup_env.ps1
```

El script automáticamente:
- Crea el entorno virtual
- Instala dependencias
- Crea la base de datos
- Configura variables de Stripe

### Opción B: Manual

```powershell
# 1. Crear entorno virtual
python -m venv .venv

# 2. Activar entorno virtual
.\.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Crear base de datos
python create_db.py
```

## 🔐 Configuración de Stripe

### Obtener Claves de Prueba

1. Crea una cuenta en [Stripe](https://stripe.com/es)
2. Ve a tu [Dashboard](https://dashboard.stripe.com/test/apikeys)
3. Copia las claves de prueba:
   - **Secret Key** (`sk_test_...`)
   - **Publishable Key** (`pk_test_...`)

### Configurar Variables de Entorno

#### Opción A: Sesión Actual (Temporal)

```powershell
$env:STRIPE_SECRET_KEY = "sk_test_..."
$env:STRIPE_PUBLISHABLE_KEY = "pk_test_..."
$env:STRIPE_WEBHOOK_SECRET = "whsec_..." # Se obtiene después
```

> **❗ Atención:** Si ves `Error de autenticación con Stripe` al intentar crear una sesión de pago, es muy probable que
> 1. `STRIPE_SECRET_KEY` esté vacío o no configurado, o
> 2. se haya usado por error la **clave pública** (`pk_...`) en lugar de la secreta (`sk_...`).
>
> Revisa las variables de entorno y asegúrate de usar la clave `sk_test_...` adecuada.

#### Opción B: Persistente (Permanente en Windows)

```powershell
setx STRIPE_SECRET_KEY "sk_test_..."
setx STRIPE_PUBLISHABLE_KEY "pk_test_..."
setx STRIPE_WEBHOOK_SECRET "whsec_..."
```

Cierra la terminal y abre una nueva para que los cambios surtan efecto.

## 📧 Configuración de Email Automático

### Características
- **Confirmación de pagos**: Email automático cuando se procesa un pago exitoso
- **Actualización de estados**: Notificación cuando cambia el estado de una reparación
- **Facturas**: Envío de facturas por email

### Configuración Rápida

```powershell
# Ejecutar el asistente de configuración
.\configure_email.ps1
```

### Configuración Manual

#### Para Gmail (Recomendado con 2FA)
```powershell
# Variables de entorno necesarias
$env:MAIL_SERVER = "smtp.gmail.com"
$env:MAIL_PORT = "587"
$env:MAIL_USE_TLS = "true"
$env:MAIL_USE_SSL = "false"
$env:MAIL_USERNAME = "tu-email@gmail.com"
$env:MAIL_PASSWORD = "tu-contraseña-de-aplicación"
$env:MAIL_DEFAULT_SENDER = "noreply@androtech.com"
```

**Configuración de Gmail:**
1. Ve a [Google Account Settings](https://myaccount.google.com/security)
2. Activa la **Verificación en 2 pasos**
3. Ve a **Contraseñas de aplicaciones**
4. Genera una contraseña para "AndroTech"
5. Usa esa contraseña de 16 caracteres en `MAIL_PASSWORD`

#### Para Outlook/Hotmail
```powershell
$env:MAIL_SERVER = "smtp-mail.outlook.com"
$env:MAIL_PORT = "587"
$env:MAIL_USE_TLS = "true"
$env:MAIL_USE_SSL = "false"
$env:MAIL_USERNAME = "tu-email@outlook.com"
$env:MAIL_PASSWORD = "tu-contraseña-normal"
$env:MAIL_DEFAULT_SENDER = "noreply@androtech.com"
```

### Alternar entre Proveedores

```powershell
# Script para cambiar fácilmente entre Gmail y Outlook
python switch_email_config.py
```

### Probar Configuración Específica

```powershell
# Probar Gmail específicamente
python test_gmail.py

# Probar configuración general
python test_email_console.py
```

## ▶️ Ejecutar la Aplicación

```powershell
# Asegúrate de tener el venv activo
.\.venv\Scripts\Activate.ps1

# Ejecutar Flask en modo desarrollo
python app.py
```

La app estará disponible en: `http://127.0.0.1:5000`

### Credenciales de Prueba

- **Usuario**: `Manuel`
- **Contraseña**: (verificar en `setup_test_data.py`)

## 🧪 Probar Pagos Públicos Localmente

### Paso 1: Obtener Secret de Webhook

```powershell
# Instala Stripe CLI desde: https://stripe.com/docs/stripe-cli
stripe login

# Desde la carpeta del proyecto, ejecuta en otra terminal:
stripe listen --forward-to localhost:5000/stripe/webhook
```

Copía el `Webhook Signing Secret` (formato: `whsec_...`) y configúralo:

```powershell
$env:STRIPE_WEBHOOK_SECRET = "whsec_..."
```

### Paso 2: Simular un Pago

1. Abre `http://127.0.0.1:5000/consulta`
2. Introduce un número de reparación (ej: `1`)
3. Si tiene precio y no está pagada, verás el botón "Pagar con tarjeta"
4. Introduce el email del cliente
5. En Stripe Checkout, usa tarjeta de prueba: `4242 4242 4242 4242`
   - CVC: cualquier número (ej: `123`)
   - Fecha: mes/año futuros

### Paso 3: Verificar Pago

- El webhook actualizará automáticamente el estado en BD
- Vuelve a la consulta y verás "Pago Confirmado"
- En el dashboard verás el pago registrado

## � Probar Sistema de Email

### Modo de Prueba (Sin Envío Real)

Por defecto, el sistema imprime emails en consola para evitar problemas de configuración SMTP:

```powershell
# Ejecutar pruebas de email
python test_email_console.py
```

Verás en consola los emails que se enviarían (confirmaciones de pago, actualizaciones de estado, facturas).

### Activar Envío Real de Emails

1. **Configura credenciales SMTP válidas** en `.env`:
   ```env
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USE_TLS=true
   MAIL_USERNAME=tu-email@gmail.com
   MAIL_PASSWORD=tu-contraseña-app
   ```

2. **Restaura envío real**:
   ```powershell
   python restore_email_sending.py
   ```

3. **Reinicia la aplicación** para aplicar cambios.

### Tipos de Emails Automáticos

- **Confirmación de pago**: Se envía automáticamente al procesar un pago exitoso
- **Actualización de estado**: Se envía cuando cambia el estado de una reparación
- **Factura**: Se puede enviar manualmente desde el dashboard

## �📁 Estructura del Proyecto

```
AndroTech/
├── app.py                    # Aplicación Flask principal
├── create_db.py             # Script para crear BD
├── requirements.txt         # Dependencias Python
├── README.md               # Este archivo
├── .env.example            # Template de variables de entorno
├── setup_env.ps1           # Script automático de setup (Windows)
├── AUDIT_PAGO_PUBLICO.md   # Análisis de validaciones de pago
│
├── database/
│   └── andro_tech.db       # Base de datos SQLite
│
├── static/
│   ├── css/
│   │   └── style.css
│   └── imagenes/           # (falta agregar imágenes)
│
├── templates/
│   ├── base.html           # Plantilla base
│   ├── consulta.html       # Consulta pública + pago
│   ├── pago_exito.html     # Página de éxito
│   ├── editar_reparacion.html  # Gestión de pagos internos
│   ├── dashboard.html      # Dashboard administrativo
│   ├── reparaciones.html   # Listado con filtros
│   └── ... (otras plantillas)
│
└── utils/
    └── pdf_generator.py    # Generador de presupuestos/facturas
```

## 🔒 Consideraciones de Seguridad

✅ **Implementadas**:
- No se manejan datos de tarjeta (Stripe lo hace)
- Verificación por email antes de pagos públicos
- Webhook valida firma de Stripe
- Contraseñas hasheadas (werkzeug.security)
- Variables sensibles en entorno

⚠️ **Producción**:
- Usar HTTPS obligatoriamente
- Cambiar SECRET_KEY en Flask a valor aleatorio
- Usar base de datos robusta (PostgreSQL en lugar de SQLite)
- Configurar rate-limiting en servidor
- Usar reverse proxy (nginx) con SSL

## 📝 Archivos Clave

### Backend
- [app.py](app.py): Routes, autenticación, pagos públicos, webhooks
- [create_db.py](create_db.py): Schema de BD (clientes, reparaciones, usuarios)
- [utils/pdf_generator.py](utils/pdf_generator.py): Generación de PDF

### Frontend
- [templates/consulta.html](templates/consulta.html): Página pública de consulta + pago
- [templates/editar_reparacion.html](templates/editar_reparacion.html): UI de pagos internos
- [templates/dashboard.html](templates/dashboard.html): Dashboard con KPIs

## 📊 Flujo de Pago Público

```
1. Cliente entra a /consulta
2. Introduce # reparación
3. Si existe + tiene precio + no pagada → muestra formulario
4. Cliente verifica email
5. Envía email al endpoint /publico/pagar/<id>
6. App valida reparación + email
7. Crea sesión Stripe Checkout
8. Stripe redirige a página de pago
9. Cliente paga con tarjeta
10. Stripe envía webhook a /stripe/webhook
11. App valida webhook y marca como pagado
12. Cliente ve confirmación en /pago_exito
```

## 🐛 Troubleshooting

### Error: "stripe module not found"
```powershell
pip install stripe
```

### Error: "STRIPE_SECRET_KEY not configured"
Verifica que configuraste las variables de entorno. Usa:
```powershell
$env:STRIPE_SECRET_KEY # debe mostrar tu clave
```

### Error: "Database locked"
Cierra la app y vuelve a ejecutar:
```powershell
python app.py
```

### Webhook no funciona localmente
Verifica que ejecutaste:
```powershell
stripe listen --forward-to localhost:5000/stripe/webhook
```

## 📚 Documentación Adicional

- [Guía de Stripe Checkout](https://stripe.com/docs/payments/checkout)
- [Documentación de Webhooks Stripe](https://stripe.com/docs/webhooks)
- [Stripe CLI Setup](https://stripe.com/docs/stripe-cli)
- [Flask Documentation](https://flask.palletsprojects.com/)

## 🚀 Próximas Mejoras Planeadas

- [ ] Implementar Audit Log (historial de cambios)
- [ ] Gráficas interactivas (Chart.js) en dashboard
- [ ] Notificaciones por email
- [ ] Soporte para múltiples idiomas
- [ ] Tests automatizados
- [ ] Despliegue a producción (gunicorn, nginx)

## 📄 Licencia

Este proyecto es de uso interno para AndroTech.

## 👨‍💻 Soporte

Para reportar errores o sugerencias, contacta con el administrador del proyecto.

---

**Última actualización**: Febrero 2026
