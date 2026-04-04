# AndroTech - Sistema de Gestion de Reparaciones

Aplicacion web completa para la gestion de un taller de reparacion de dispositivos moviles y tablets. Desarrollada con Flask (Python) como proyecto de 2 SMR.

---

## Funcionalidades principales

### Gestion de reparaciones
- CRUD completo de reparaciones con estados (Pendiente, En proceso, Terminado, Entregado)
- Historial de cambios de estado con registro de usuario y fecha
- Subida de fotos con drag & drop y galeria con lightbox
- Firma digital del cliente mediante canvas tactil
- Notas internas por reparacion (con marcado de importancia)
- Piezas utilizadas con autocompletado desde inventario
- Generacion de ticket de recogida con codigo QR
- Exportacion de presupuestos y facturas en PDF

### Gestion de clientes
- CRUD completo de clientes
- Historial de reparaciones por cliente
- Exportacion del historial a PDF
- Consulta publica de estado de reparacion (sin login)

### Dashboard administrativo
- KPIs en tiempo real: clientes, reparaciones, ingresos, pendientes
- Graficos interactivos con Chart.js (estados, dispositivos, ingresos mensuales, tecnicos)
- Alertas de reparaciones atrasadas (sin actividad > 7 dias)
- Distribucion de estados y dispositivos mas reparados
- Auditoria de eventos reciente

### Inventario de piezas
- CRUD de piezas con categorias (Pantallas, Baterias, Conectores, Placas, Carcasas, Accesorios)
- Control de stock con alertas de stock bajo
- Precio de coste y venta por pieza
- Busqueda por API JSON para autocompletado

### Calendario
- Vista calendario con FullCalendar (mes, semana, lista)
- Eventos coloreados segun estado de la reparacion
- Locale en español

### Sistema de pagos
- Integracion con Stripe Checkout para pagos publicos con tarjeta
- Webhook para confirmacion automatica de pagos
- Registro de metodo y fecha de pago
- Pagina publica de consulta y pago

### Notificaciones por email
- Confirmacion de pago automatica
- Notificacion de cambio de estado
- Bienvenida a nuevos clientes
- Aviso de nueva reparacion registrada
- Templates HTML profesionales en español

### Seguridad
- Autenticacion con contraseñas hasheadas (Werkzeug)
- Validacion de contraseñas: minimo 8 caracteres, mayuscula, minuscula y numero
- Roles de usuario: administrador y tecnico
- Proteccion CSRF en todos los formularios
- Cabeceras de seguridad (X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
- Audit log con registro de IP y timestamp
- Validacion de precios y ficheros subidos

### PWA (Progressive Web App)
- Instalable en movil y escritorio
- Service Worker con estrategia network-first
- Manifest con tema corporativo

### Otras funcionalidades
- Busqueda global de clientes y reparaciones
- Exportacion a CSV (reparaciones, clientes)
- Modo oscuro completo
- Logging estructurado en JSON con rotacion de ficheros
- Diseño responsive (movil, tablet, escritorio)

---

## Tecnologias utilizadas

| Capa | Tecnologia |
|------|-----------|
| Backend | Python 3.8+, Flask 3.1 |
| Base de datos | SQLite3 |
| Frontend | Bootstrap 5.3, Bootstrap Icons 1.11 |
| Graficos | Chart.js 4.4 |
| Calendario | FullCalendar 6.1 |
| Firma digital | Signature Pad 4.2 |
| PDF | ReportLab 4.4 |
| Pagos | Stripe 14.4 |
| Email | Flask-Mail (SMTP) |
| PWA | Service Worker, Web App Manifest |

---

## Requisitos previos

- Python 3.8 o superior
- pip (gestor de paquetes Python)
- Git (opcional, para clonar el repositorio)

---

## Instalacion

### 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd AndroTech
```

### 2. Crear y activar entorno virtual

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux/Mac:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Crear la base de datos

```bash
python create_db.py
```

### 5. Ejecutar la aplicacion

```bash
python app.py
```

La aplicacion estara disponible en: **http://127.0.0.1:5000**

---

## Configuracion

### Variables de entorno

Crea un fichero `.env` en la raiz del proyecto (o configura variables de entorno del sistema):

```env
# Flask
SECRET_KEY=tu-clave-secreta-aqui

# Stripe (opcional - para pagos con tarjeta)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email (opcional - para notificaciones)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=tu-email@gmail.com
MAIL_PASSWORD=tu-contraseña-de-aplicacion
MAIL_DEFAULT_SENDER=noreply@androtech.com
```

### Configuracion de Gmail

Si usas Gmail para enviar emails:

1. Activa la **Verificacion en 2 pasos** en tu cuenta de Google
2. Ve a **Contraseñas de aplicaciones** en la configuracion de seguridad
3. Genera una contraseña para "AndroTech"
4. Usa esa contraseña de 16 caracteres en `MAIL_PASSWORD`

### Configuracion de Stripe (pagos)

1. Crea una cuenta en [Stripe](https://stripe.com/es)
2. Copia las claves de prueba desde el [Dashboard](https://dashboard.stripe.com/test/apikeys)
3. Para webhooks locales, instala [Stripe CLI](https://stripe.com/docs/stripe-cli):
   ```bash
   stripe listen --forward-to localhost:5000/stripe/webhook
   ```

---

## Credenciales por defecto

| Usuario | Contraseña | Rol |
|---------|-----------|-----|
| admin | test1234 | Administrador |

> Cambia la contraseña del administrador tras el primer inicio de sesion.

---

## Estructura del proyecto

```
AndroTech/
├── app.py                     # Aplicacion Flask principal (rutas, logica)
├── db.py                      # Conexion a base de datos SQLite
├── auth.py                    # Decoradores de autenticacion y roles
├── audit.py                   # Sistema de auditoria
├── alerts.py                  # Calculo de alertas de reparaciones
├── historial.py               # Registro de historial de estados
├── create_db.py               # Script para crear la base de datos
├── requirements.txt           # Dependencias Python
├── .env                       # Variables de entorno (no incluido en git)
│
├── database/
│   └── andro_tech.db          # Base de datos SQLite
│
├── static/
│   ├── css/
│   │   └── style.css          # Estilos personalizados (2500+ lineas)
│   ├── imagenes/
│   │   └── logo.jpg           # Logo de AndroTech
│   ├── uploads/
│   │   ├── reparaciones/      # Fotos subidas de reparaciones
│   │   └── firmas/            # Firmas digitales guardadas
│   ├── favicon.svg            # Icono de la aplicacion
│   ├── sw.js                  # Service Worker (PWA)
│   └── manifest.json          # Manifiesto PWA
│
├── templates/                 # Plantillas Jinja2 (35 ficheros)
│   ├── base.html              # Plantilla base con navbar y footer
│   ├── login.html             # Inicio de sesion
│   ├── dashboard.html         # Panel de control con graficos
│   ├── clientes.html          # Listado de clientes
│   ├── reparaciones.html      # Listado de reparaciones
│   ├── editar_reparacion.html # Edicion con fotos, notas, piezas, firma
│   ├── inventario.html        # Gestion de inventario
│   ├── calendario.html        # Vista calendario
│   ├── firmar_reparacion.html # Captura de firma digital
│   ├── emails/                # Plantillas de email HTML
│   │   ├── nueva_reparacion.html
│   │   ├── repair_status_update.html
│   │   ├── payment_confirmation.html
│   │   └── bienvenida_cliente.html
│   └── ...
│
├── utils/
│   ├── security.py            # CSRF, validacion de contraseñas y precios
│   ├── email_service.py       # Servicio de envio de emails
│   └── pdf_generator.py       # Generador de PDFs
│
└── logs/                      # Logs de la aplicacion (JSON rotativo)
```

---

## Rutas principales

| Ruta | Metodo | Descripcion | Acceso |
|------|--------|-------------|--------|
| `/` | GET | Pagina de inicio | Publico |
| `/login` | GET/POST | Inicio de sesion | Publico |
| `/dashboard` | GET | Panel de control | Login |
| `/clientes` | GET | Listado de clientes | Login |
| `/clientes/nuevo` | GET/POST | Crear cliente | Login |
| `/reparaciones` | GET | Listado de reparaciones | Login |
| `/reparaciones/nueva` | GET/POST | Crear reparacion | Login |
| `/reparaciones/editar/<id>` | GET/POST | Editar reparacion | Login |
| `/inventario` | GET | Inventario de piezas | Admin |
| `/calendario` | GET | Vista calendario | Login |
| `/consulta` | GET/POST | Consulta publica | Publico |
| `/mis-reparaciones` | GET/POST | Reparaciones del cliente | Publico |
| `/admin/usuarios` | GET | Gestion de usuarios | Admin |
| `/buscar` | GET | Busqueda global | Login |

---

## Flujo de uso tipico

1. **Recepcion**: El tecnico registra al cliente y crea una nueva reparacion con fotos del dispositivo
2. **Diagnostico**: Se actualizan notas internas y se añaden piezas del inventario
3. **Reparacion**: Se cambia el estado a "En proceso" (se notifica al cliente por email)
4. **Finalizacion**: Se marca como "Terminado", se genera presupuesto/factura PDF
5. **Entrega**: El cliente firma digitalmente, se genera ticket de recogida con QR
6. **Pago**: El cliente paga online (Stripe) o en tienda, se registra el pago

---

## Solucion de problemas

### "Module not found" al ejecutar

Asegurate de tener el entorno virtual activado:
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### VS Code no reconoce los imports

Selecciona el interprete del entorno virtual:
1. `Ctrl + Shift + P` > `Python: Select Interpreter`
2. Selecciona `.venv/Scripts/python.exe`

### "Database locked"

Cierra la aplicacion y vuelve a ejecutar `python app.py`. SQLite solo permite una conexion de escritura simultanea.

### Emails no se envian

Verifica las credenciales SMTP en `.env`. Para Gmail necesitas una "contraseña de aplicacion", no tu contraseña normal.

---

## Licencia

Proyecto academico de uso interno para AndroTech - Taller de reparacion de dispositivos moviles. Desarrollado como proyecto de 2 SMR.

---

**Desarrollado por**: Manuel - 2 SMR
**Ultima actualizacion**: Abril 2026
