<div align="center">

# AndroTech

**Sistema Web de Gestión Integral para Taller Técnico de Reparaciones**

*Proyecto Intermodular · C.F.G.M. Sistemas Microinformáticos y Redes*
*I.E.S. La Marisma — Huelva · Curso 2025/2026*

[![En producción](https://img.shields.io/badge/En_producción-androtech--production.up.railway.app-2B8AC4?style=for-the-badge)](https://androtech-production.up.railway.app)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Railway](https://img.shields.io/badge/Railway-0B0D0E?style=for-the-badge&logo=railway&logoColor=white)](https://railway.app/)

</div>

---

## Índice

1. [Sobre el proyecto](#sobre-el-proyecto)
2. [Acceso a la aplicación](#acceso-a-la-aplicación)
3. [Documentación](#documentación)
4. [Arquitectura técnica](#arquitectura-técnica)
5. [Estructura del repositorio](#estructura-del-repositorio)
6. [Instalación local](#instalación-local)
7. [Funcionalidades implementadas](#funcionalidades-implementadas)
8. [Autoría y créditos](#autoría-y-créditos)

---

## Sobre el proyecto

AndroTech es una aplicación web completa que digitaliza la gestión integral de un taller técnico de reparaciones, desde que el cliente solicita el servicio hasta que recoge el dispositivo y paga. El proyecto nace para resolver una problemática real detectada durante la Formación en Centros de Trabajo (FCT) en un taller de Huelva que gestionaba toda su actividad de forma manual.

El sistema está desarrollado íntegramente con Python y Flask, sobre SQLite, con una arquitectura modular MVC y desplegado en producción con redespliegue automático conectado a GitHub.

> **Métricas del proyecto:** 58 rutas Flask · 12 tablas relacionadas · 39 templates · 31 permisos granulares · ~3.500 líneas de código backend · ~3.200 líneas de CSS propio · 6 meses de desarrollo · ~180 horas de dedicación.

---

## Acceso a la aplicación

### Aplicación en producción

La aplicación está accesible públicamente en:

**[androtech-production.up.railway.app](https://androtech-production.up.railway.app)**

### Credenciales de evaluación

Para acceder al panel administrativo y evaluar todas las funcionalidades:

| Campo | Valor |
|-------|-------|
| Usuario | `admin` |
| Contraseña | `admin123` |

### Datos de demostración

Para poblar la base de datos con datos de demostración (clientes, reparaciones, inventario), iniciar sesión como administrador y acceder a:

```
/admin/seed-demo?key=demo2026
```

### Pago de prueba con Stripe

Para probar el flujo de pago online sin cargo real, utilizar la tarjeta de prueba de Stripe:

| Campo | Valor |
|-------|-------|
| Número | `4242 4242 4242 4242` |
| Caducidad | Cualquier fecha futura |
| CVC | Cualquier número de 3 dígitos |

---

## Documentación

Toda la documentación del proyecto está organizada en la carpeta [`docs/`](./docs):

### Memoria del proyecto

Documentación oficial del Proyecto Intermodular:

- [Memoria completa (Word)](./docs/memoria/AndroTech_Documento_Proyecto.docx)
- [Capítulo 1 — Introducción y objetivos](./docs/memoria/AndroTech_Documento_Proyecto_Cap1.md)
- [Capítulo 2 — Análisis y diseño](./docs/memoria/AndroTech_Documento_Proyecto_Cap2.md)
- [Capítulos 3 y 4 — Implementación](./docs/memoria/AndroTech_Documento_Proyecto_Cap3_Cap4.md)
- [Capítulos 5 a 7 — Pruebas, despliegue y conclusiones](./docs/memoria/AndroTech_Documento_Proyecto_Cap5_Cap6_Cap7_Final.md)
- [Manual de Usuario](./docs/memoria/AndroTech_Manual_Usuario.md)
- [Manual de Instalación](./docs/memoria/AndroTech_Manual_Instalacion.md)

### Defensa oral

Materiales para la presentación y evaluación:

- [Presentación HTML interactiva](./docs/defensa/AndroTech_Presentacion_Final.html) — 20 diapositivas
- [Posibles preguntas del tribunal](./docs/defensa/AndroTech_Preguntas_Tribunal.md)
- [Guía técnica del código](./docs/defensa/GUIA_CODIGO.md)

### Documentación técnica

Configuración y guías para desarrolladores:

- [Instalación en un equipo nuevo](./docs/tecnico/INSTALAR_EN_PORTATIL.md)
- [Configuración del webhook de Stripe](./docs/tecnico/WEBHOOK_SETUP.md)
- [Pruebas del flujo de pago](./docs/tecnico/TESTING_PAYMENTS.md)
- [Configuración de email SMTP](./docs/tecnico/EMAIL_SETUP.md)
- [Configuración Gmail con App Password](./docs/tecnico/GMAIL_SETUP.md)

---

## Arquitectura técnica

### Stack tecnológico

| Capa | Tecnologías |
|------|-------------|
| **Backend** | Python 3.12 · Flask 3.1 · Werkzeug · Flask-Limiter |
| **Base de datos** | SQLite3 con 12 tablas relacionadas (sin ORM, SQL parametrizado) |
| **Servicios externos** | Stripe API (pagos online con webhook validado) · Gmail SMTP |
| **Documentos** | ReportLab (PDF con QR e IVA al 21%) · Pillow |
| **Frontend** | Bootstrap 5.3 · Jinja2 · Chart.js · FullCalendar · Signature Pad |
| **Producción** | Gunicorn (WSGI) en Railway.app con HTTPS automático |
| **PWA** | Service Worker con estrategia network-first y manifest.json |
| **Control de versiones** | Git con GitHub, redespliegue automático en cada push |

### Patrón arquitectónico

El proyecto sigue un patrón **MVC** adaptado a Flask con tres capas claramente separadas:

- **Modelo:** SQL directo con `sqlite3` y parámetros enlazados para prevenir inyección SQL.
- **Vista:** 39 templates Jinja2 que heredan de `base.html`, con CSS propio y modo oscuro persistente.
- **Controlador:** 58 rutas en `app.py` apoyadas en módulos auxiliares con responsabilidades específicas (`auth.py`, `audit.py`, `alerts.py`, `historial.py` y la carpeta `utils/`).

### Seguridad multicapa

Seis capas de protección independientes:

- Protección **CSRF** propia con tokens generados por sesión (`secrets.token_urlsafe`)
- Hash de contraseñas con **PBKDF2 + SHA-256** (Werkzeug)
- **Rate limiting** en endpoint de login (5 intentos por minuto)
- Headers HTTP de seguridad en `after_request` (X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
- Validación criptográfica de **webhooks de Stripe** (`construct_event`)
- **Auditoría completa** de eventos críticos en formato JSON estructurado

---

## Estructura del repositorio

```
Androtech/
├── app.py                      Aplicación Flask principal (58 rutas)
├── auth.py                     Sistema de permisos y decoradores
├── audit.py                    Registro de auditoría
├── alerts.py                   Cálculo de alertas inteligentes
├── historial.py                Transiciones de estado
├── db.py                       Conexión SQLite
│
├── utils/                      Servicios auxiliares
│   ├── email_service.py        Envío de emails (SMTP nativo)
│   ├── pdf_generator.py        Generación de PDF con ReportLab
│   └── security.py             Validaciones CSRF
│
├── templates/                  Plantillas HTML (Jinja2)
├── static/                     CSS, imágenes, PWA
├── database/                   Base de datos SQLite
│
├── docs/                       Documentación del proyecto
│   ├── memoria/                Memoria del TFG y manuales
│   ├── defensa/                Materiales para la defensa oral
│   └── tecnico/                Guías de configuración
│
├── scripts/                    Scripts auxiliares
│   ├── create_db.py            Inicializador de la BD
│   └── check_*.py              Utilidades de diagnóstico
│
├── .env.example                Plantilla de variables de entorno
├── requirements.txt            Dependencias Python
├── Procfile                    Comando de arranque (Gunicorn)
├── runtime.txt                 Versión de Python (3.12.0)
└── README.md                   Este documento
```

---

## Instalación local

Para instalar y ejecutar el proyecto en un equipo de desarrollo. Para una guía detallada paso a paso, consultar [docs/tecnico/INSTALAR_EN_PORTATIL.md](./docs/tecnico/INSTALAR_EN_PORTATIL.md).

### Requisitos previos

- Python 3.12
- Git
- Una cuenta de Stripe (modo test) y una App Password de Gmail para las funcionalidades completas

### Pasos

```bash
# Clonar el repositorio
git clone https://github.com/manuelcortes07/Androtech.git
cd Androtech

# Crear y activar el entorno virtual (Windows)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Instalar dependencias
pip install -r requirements.txt

# Crear el fichero .env (copiar plantilla y rellenar valores reales)
copy .env.example .env

# Inicializar la base de datos
python scripts/create_db.py

# Arrancar la aplicación
python app.py
```

La aplicación estará disponible en `http://127.0.0.1:5000`.

> **Nota:** las claves de Stripe y la App Password de Gmail deben configurarse en el fichero `.env` antes de probar las funcionalidades de pago online y notificación por email.

---

## Funcionalidades implementadas

### Portal público (sin autenticación)

- Consulta del estado de una reparación mediante número y email del cliente
- Solicitud de nueva reparación a través de formulario web
- Pago online con tarjeta bancaria mediante Stripe Checkout
- Acceso al historial completo de reparaciones del cliente
- Botón de contacto directo por WhatsApp
- Modo oscuro persistente y aplicación instalable como PWA

### Panel técnico (rol Técnico — 17 permisos)

- Gestión completa de clientes y reparaciones (CRUD)
- Cambio de estado con registro automático en historial inmutable
- Subida de fotos con drag & drop y previsualización
- Recogida de firma digital del cliente sobre canvas HTML5
- Notas internas privadas por reparación
- Asignación de piezas de inventario con descuento automático de stock
- Generación al vuelo de presupuestos y facturas en PDF

### Panel administrativo (rol Admin — 31 permisos)

- Dashboard con 15 KPIs en tiempo real y 4 gráficos Chart.js
- Cálculo de ingresos, IVA desglosado, tasa de cobro y tiempo medio de reparación
- Sistema de alertas inteligentes (sin presupuesto, atrasada, pago pendiente)
- Gestión completa de usuarios con asignación de roles
- Inventario de piezas con alertas de stock mínimo
- Calendario de reparaciones con FullCalendar
- Búsqueda global a través de todas las entidades
- Log de auditoría completo con eventos críticos en formato JSON
- Panel de recursos de defensa centralizado en `/admin/defensa`

### Integraciones externas

- **Stripe**: pagos online con validación criptográfica del webhook
- **Gmail SMTP**: notificaciones automáticas al cliente con plantillas HTML y PDF adjuntos
- **Railway**: despliegue continuo con HTTPS automático

---

## Autoría y créditos

| | |
|---|---|
| **Autor** | Manuel Cortés Contreras |
| **Tutor académico** | Juan Alonso Limón Limón |
| **Centro educativo** | I.E.S. La Marisma — Huelva |
| **Ciclo formativo** | C.F.G.M. Sistemas Microinformáticos y Redes |
| **Curso académico** | 2025 / 2026 |
| **Repositorio** | [github.com/manuelcortes07/Androtech](https://github.com/manuelcortes07/Androtech) |
| **Aplicación en producción** | [androtech-production.up.railway.app](https://androtech-production.up.railway.app) |

---

<div align="center">

**Proyecto académico desarrollado para el Proyecto Intermodular del C.F.G.M. SMR.**

*Abril de 2026*

</div>
