# AndroTech — Sistema de Gestión para Taller Técnico

**Proyecto Intermodular · C.F.G.M. Sistemas Microinformáticos y Redes**  
**I.E.S. La Marisma · Huelva · Curso 2025/2026**

---

## Descripción

AndroTech es una aplicación web completa desarrollada con Flask para la gestión integral de un taller técnico de reparación de dispositivos móviles y ordenadores. El sistema digitaliza todos los procesos del taller: desde la recepción de una reparación hasta la facturación y cobro al cliente, pasando por la comunicación automática en cada etapa del proceso.

El proyecto está basado en el taller real **DoJaMac Informática – Andropple**, ubicado en el Paseo de la Independencia, 19, Local Derecha, 21002 Huelva.

---

## Características principales

### Gestión de reparaciones
- CRUD completo de clientes y reparaciones
- Sistema de estados con transiciones controladas: `Pendiente → En Proceso → Terminado → Entregado`
- Historial completo de cambios de estado con registro de usuario y fecha
- Fotos de la reparación con drag & drop
- Notas internas por reparación
- Firma digital del cliente

### Panel de administración
- Dashboard con KPIs en tiempo real: clientes, reparaciones activas, ingresos, tasa de cobro
- Gráficos interactivos con Chart.js: ingresos por mes, reparaciones por técnico, distribución de estados
- Alertas inteligentes: reparaciones atrasadas, pendientes de pago, sin presupuesto
- Exportación a CSV compatible con Excel en español
- Calendario de citas con FullCalendar
- Gestión de inventario de piezas
- Búsqueda global en tiempo real
- Sistema de auditoría con registro JSON de todos los eventos críticos

### Portal público (sin login)
- Consulta del estado de reparación por ID y email
- Formulario de solicitud de reparación online
- Alternativa de contacto por WhatsApp
- Páginas informativas: servicios, sobre nosotros, contacto

### Pagos online con Stripe
- Checkout público seguro para que el cliente pague sin necesidad de cuenta
- Webhook validado criptográficamente para confirmación automática del pago
- Validaciones completas: importe, estado, duplicados
- Marcado automático de la reparación como pagada tras confirmación

### Comunicación automática
- Emails automáticos al cliente en cambios de estado (Flask-Mail)
- Confirmación de pago con detalle de la reparación
- 5 plantillas HTML profesionales
- Configuración SMTP mediante variables de entorno

### Generación de documentos PDF
- Presupuestos y facturas con ReportLab
- Diseño profesional con logo, datos de empresa, IVA al 21% y código QR
- Descarga directa desde el panel de técnico

### Seguridad
- Protección CSRF implementada desde cero en todas las rutas POST
- Hash seguro de contraseñas con Werkzeug
- Sistema de roles granular: 31 permisos en 5 categorías (admin / técnico)
- Rate limiting en login: 5 intentos por minuto por IP (Flask-Limiter)
- Headers HTTP de seguridad: `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`
- Sesiones con expiración automática a las 6 horas
- Logging estructurado en JSON con rotación de ficheros (5 MB, 3 backups)
- Auditoría de eventos críticos con IP, usuario y timestamp

### PWA (Progressive Web App)
- Service Worker para funcionamiento offline básico
- Manifest con iconos multi-resolución (32px a 512px)
- Instalable en dispositivos móviles

---

## Stack tecnológico

| Componente | Tecnología |
|------------|------------|
| Backend | Python · Flask 3.1.2 |
| Base de datos | SQLite3 |
| Templates | Jinja2 · Bootstrap 5.3 |
| Gráficos | Chart.js (CDN) |
| Animaciones | ScrollReveal (CDN) |
| Calendario | FullCalendar (CDN) |
| Firma digital | Signature Pad (CDN) |
| Pagos | Stripe (Checkout + Webhooks) |
| Emails | Flask-Mail 0.10.0 |
| PDFs | ReportLab 4.4.10 |
| Seguridad | Flask-Limiter 4.1.1 · Werkzeug |
| Variables de entorno | python-dotenv |

---

## Estructura del proyecto

```
AndroTech/
├── app.py                        # Aplicación Flask principal (41 rutas)
├── db.py                         # Helpers de conexión SQLite
├── auth.py                       # Autenticación, roles y 31 permisos
├── audit.py                      # Sistema de auditoría con logger JSON
├── alerts.py                     # Cálculo de alertas inteligentes
├── historial.py                  # Historial de cambios de estado
├── create_db.py                  # Inicialización de la base de datos
├── requirements.txt              # Dependencias Python
├── .env.example                  # Plantilla de variables de entorno
│
├── utils/
│   ├── email_service.py          # EmailService con Flask-Mail
│   ├── pdf_generator.py          # InvoiceGenerator con ReportLab
│   └── security.py               # CSRF y validaciones de seguridad
│
├── templates/                    # 38 templates Jinja2
│   ├── base.html                 # Layout base con navbar y footer
│   ├── index.html                # Home pública rediseñada
│   ├── consulta.html             # Consulta pública de reparaciones
│   ├── solicitar_reparacion.html # Formulario público de solicitud
│   ├── dashboard.html            # Panel de administración con KPIs
│   ├── emails/                   # 5 plantillas HTML de email
│   └── ...                       # Resto de vistas
│
├── static/
│   ├── css/style.css             # Estilos propios sobre Bootstrap 5
│   ├── imagenes/logo.jpg         # Logo del taller
│   └── favicons/                 # Iconos en 8 resoluciones
│
└── database/
    └── andro_tech.db             # Base de datos SQLite (generada en runtime)
```

---

## Base de datos

El sistema utiliza **12 tablas SQLite**:

| Tabla | Descripción |
|-------|-------------|
| `clientes` | Datos de clientes del taller |
| `reparaciones` | Reparaciones con estado, precio y pago |
| `usuarios` | Usuarios del sistema con rol |
| `reparaciones_historial` | Historial de cambios de estado |
| `fotos_reparacion` | Fotos adjuntas a cada reparación |
| `notas_reparacion` | Notas internas por reparación |
| `inventario_piezas` | Stock de piezas con alertas de mínimo |
| `piezas_reparacion` | Piezas usadas en cada reparación |
| `solicitudes_reparacion` | Solicitudes web de clientes |
| `roles` | Roles del sistema con permisos |
| `permisos_rol` | Tabla de permisos granulares |
| `audit_log` | Log de auditoría con JSON estructurado |

---

## Instalación y ejecución

### Requisitos previos
- Python 3.10 o superior
- pip

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/manuelcortes07/Androtech.git
cd Androtech

# 2. Crear entorno virtual
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus claves de Stripe y SMTP

# 5. Inicializar la base de datos
python create_db.py

# 6. Ejecutar la aplicación
python app.py
```

La aplicación estará disponible en `http://127.0.0.1:5000`

### Variables de entorno requeridas

```env
SECRET_KEY=tu_clave_secreta_aqui
STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=tu_email@gmail.com
MAIL_PASSWORD=tu_contraseña_de_aplicacion
```

---

## Credenciales de prueba

```
Usuario admin:    admin / admin123
Usuario técnico:  tecnico / tecnico123
```

> ⚠️ Cambiar las credenciales en cualquier despliegue en producción.

---

## Rutas principales

| Ruta | Acceso | Descripción |
|------|--------|-------------|
| `/` | Público | Home con estadísticas del taller |
| `/consulta` | Público | Consulta de reparación por ID y email |
| `/solicitar-reparacion` | Público | Formulario de solicitud online |
| `/login` | Público | Acceso al panel técnico |
| `/dashboard` | Admin/Técnico | Panel principal con KPIs y gráficos |
| `/clientes` | Admin/Técnico | Gestión de clientes |
| `/reparaciones` | Admin/Técnico | Gestión de reparaciones |
| `/admin/solicitudes` | Admin | Solicitudes web pendientes |
| `/admin/usuarios` | Admin | Gestión de usuarios y roles |
| `/buscar` | Admin/Técnico | Búsqueda global |
| `/reparaciones/pdf/<id>` | Admin/Técnico | Generar PDF presupuesto/factura |
| `/stripe/webhook` | Sistema | Webhook de confirmación de pago |

---

## Autor

**Manuel Cortés Contreras**  
C.F.G.M. Sistemas Microinformáticos y Redes  
I.E.S. La Marisma · Huelva  
Proyecto Intermodular · Curso 2025/2026  
Tutor: Juan Alonso Limón Limón

---

## Licencia

Este proyecto se distribuye bajo licencia **MIT**.  
Desarrollado con fines académicos para el módulo Proyecto Intermodular del ciclo formativo de grado medio de Sistemas Microinformáticos y Redes.

---

*© 2026 AndroTech · Manuel Cortés Contreras · I.E.S. La Marisma, Huelva*
