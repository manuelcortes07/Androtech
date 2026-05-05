# 3. ANÁLISIS

## 3.1 Introducción

El análisis del sistema tiene como objetivo definir con precisión qué debe hacer la aplicación AndroTech, sin entrar todavía en cómo se va a implementar. En este capítulo se describen los requisitos funcionales y no funcionales del sistema, los casos de uso principales, el modelo lógico de datos y los menús de navegación.

El análisis parte del diagnóstico realizado en el capítulo anterior sobre la situación del taller, y toma como referencia los requisitos definidos en el anteproyecto inicial, ampliados con las nuevas funcionalidades incorporadas durante el desarrollo.

---

## 3.2 Requisitos funcionales de usuarios

El sistema identifica tres tipos de usuarios con diferentes necesidades y niveles de acceso.

**Usuario cliente (sin autenticación)**

El cliente del taller accede al sistema a través del portal público sin necesidad de registrarse ni autenticarse. Sus funcionalidades son las siguientes: consultar el estado de su reparación introduciendo el número de reparación y su dirección de correo electrónico, ver los detalles de su reparación incluyendo dispositivo, descripción, estado actual y precio, realizar el pago online de su reparación mediante tarjeta bancaria a través de Stripe, y enviar una solicitud de reparación a través del formulario web público.

**Usuario técnico (autenticación requerida)**

El técnico accede al panel de gestión con sus credenciales. Sus funcionalidades son las siguientes: consultar el listado completo de reparaciones con filtros por estado, cliente, fecha y precio, crear, editar y actualizar reparaciones asignadas, cambiar el estado de una reparación siguiendo el flujo permitido, añadir notas internas a una reparación, subir fotos del dispositivo en reparación, registrar la firma digital del cliente, consultar el inventario de piezas disponibles, registrar piezas utilizadas en una reparación, generar el PDF de presupuesto o factura de una reparación, y utilizar la búsqueda global del sistema.

**Usuario administrador (autenticación requerida, permisos completos)**

El administrador dispone de todas las funcionalidades del técnico más las siguientes: gestión completa de clientes con posibilidad de eliminación, modificación de precios de reparaciones, acceso al dashboard completo con todos los KPIs, gráficos e indicadores, gestión de usuarios del sistema y asignación de roles, consulta del log de auditoría completo, gestión de solicitudes web de clientes con opción de aceptar o rechazar, y exportación de datos a CSV.

---

## 3.3 Requisitos no funcionales

Los requisitos no funcionales del sistema se agrupan en cinco categorías.

**Usabilidad:** La interfaz debe ser intuitiva y accesible desde cualquier dispositivo. El diseño debe ser responsive y adaptarse correctamente a pantallas de móvil, tablet y escritorio. Los mensajes de error deben ser claros y en español.

**Rendimiento:** El tiempo de carga de cualquier página no debe superar los 3 segundos en condiciones normales. Las consultas a la base de datos deben estar optimizadas mediante índices en los campos más consultados.

**Seguridad:** Todas las rutas que modifiquen datos deben estar protegidas contra ataques CSRF mediante tokens de validación. Las contraseñas deben almacenarse hasheadas con Werkzeug. El acceso al panel de gestión debe requerir autenticación. El sistema debe limitar los intentos de login a 5 por minuto por IP. Las claves de API y credenciales deben gestionarse mediante variables de entorno. Los eventos críticos deben quedar registrados en el log de auditoría.

**Mantenibilidad:** El código debe estar organizado en módulos con responsabilidades claras. Las variables de entorno deben estar documentadas en un fichero `.env.example`. El esquema de la base de datos debe estar documentado y ser reproducible mediante el script `create_db.py`.

**Disponibilidad:** El sistema debe funcionar correctamente en entorno local durante el desarrollo. En producción debe ser desplegable en plataformas de hosting estándar como Railway o Render.

---

## 3.4 Diagramas de casos de uso

Se describen a continuación los casos de uso principales del sistema, organizados por actor.

**Casos de uso del cliente (sin autenticación)**

El caso de uso CU-01 es "Consultar reparación". El cliente introduce su número de reparación y email. El sistema valida que el email corresponde al cliente de esa reparación y muestra los datos: dispositivo, estado actual, descripción y precio. Si los datos no son correctos, muestra un mensaje de error.

El caso de uso CU-02 es "Pagar reparación online". El cliente accede al enlace de pago de su reparación. El sistema verifica que la reparación está terminada y no ha sido pagada previamente, y redirige al checkout de Stripe. El cliente introduce los datos de su tarjeta en la plataforma de Stripe. Stripe notifica al sistema mediante webhook. El sistema marca la reparación como pagada y envía un email de confirmación al cliente.

El caso de uso CU-03 es "Solicitar reparación". El cliente rellena el formulario público con sus datos y la descripción del problema. El sistema registra la solicitud en la base de datos y la pone a disposición del administrador para su gestión.

**Casos de uso del técnico (autenticado)**

El caso de uso CU-04 es "Gestionar reparaciones". El técnico accede al listado de reparaciones, aplica filtros si es necesario, selecciona una reparación y puede actualizar su estado, añadir notas, subir fotos o registrar la firma del cliente.

El caso de uso CU-05 es "Generar PDF". El técnico selecciona una reparación y elige el tipo de documento (presupuesto o factura). El sistema genera el PDF con los datos del taller, del cliente, de la reparación, el IVA calculado y el código QR, y lo ofrece para descarga.

**Casos de uso del administrador (autenticado)**

El caso de uso CU-06 es "Consultar dashboard". El administrador accede al panel principal y visualiza los KPIs en tiempo real, los gráficos de ingresos y reparaciones por período, las alertas inteligentes y los últimos eventos de auditoría.

El caso de uso CU-07 es "Gestionar usuarios". El administrador crea, edita o desactiva usuarios del sistema y asigna los roles y permisos correspondientes.

El caso de uso CU-08 es "Gestionar solicitudes web". El administrador consulta las solicitudes recibidas a través del formulario público, las acepta creando automáticamente el cliente y la reparación en el sistema, o las rechaza.

---

## 3.5 Diagrama lógico de datos

El modelo de datos de AndroTech está compuesto por 12 tablas relacionadas. A continuación se describe la estructura y las relaciones entre ellas.

La tabla `clientes` es la entidad central del negocio. Almacena el nombre, teléfono, email y dirección de cada cliente. Tiene relación de uno a muchos con la tabla `reparaciones`, ya que un cliente puede tener múltiples reparaciones.

La tabla `reparaciones` es la entidad principal del sistema. Almacena toda la información de cada reparación: el cliente asociado, el dispositivo, la descripción del problema, el estado actual, las fechas de entrada y salida, el precio, el tipo de documento, el estado del pago, la fecha y método de pago, y la firma digital del cliente. Tiene relaciones de uno a muchos con las tablas `fotos_reparacion`, `notas_reparacion`, `piezas_reparacion` y `reparaciones_historial`.

La tabla `reparaciones_historial` registra cada cambio de estado de una reparación, almacenando el estado anterior, el estado nuevo, la fecha del cambio y el usuario que lo realizó.

La tabla `fotos_reparacion` almacena las referencias a las fotos subidas para cada reparación, con el nombre del fichero, una descripción opcional, la fecha de subida y el usuario que la subió.

La tabla `notas_reparacion` almacena las notas internas de cada reparación, con el contenido, el usuario que la creó, la fecha y un indicador de nota importante.

La tabla `inventario_piezas` gestiona el stock de piezas del taller, con nombre, categoría, cantidad actual, cantidad mínima de alerta, precio de coste y precio de venta.

La tabla `piezas_reparacion` es la tabla de relación entre reparaciones e inventario, registrando qué piezas y en qué cantidad se han utilizado en cada reparación.

La tabla `solicitudes_reparacion` almacena las solicitudes recibidas a través del formulario público, con todos los datos del cliente, la descripción del problema, la urgencia, las preferencias de fecha y horario, y el estado de gestión.

La tabla `usuarios` almacena los usuarios del sistema con su nombre de usuario, contraseña hasheada y rol asignado.

La tabla `roles` define los roles disponibles en el sistema, con nombre, descripción y color de identificación visual.

La tabla `permisos_rol` implementa el sistema de permisos granulares, asociando permisos específicos a cada rol. El sistema dispone de 31 permisos distribuidos en 5 categorías: clientes, reparaciones, administración, inventario y sistema.

La tabla `audit_log` registra todos los eventos críticos del sistema con el tipo de evento, el usuario que lo realizó, los datos del evento en formato JSON, la dirección IP del cliente y el timestamp.

---

## 3.6 Menús de navegación

**Navegación pública (sin autenticación)**

La barra de navegación pública incluye los siguientes enlaces: Inicio, Servicios, Sobre Nosotros, Consulta y el botón de Acceso Técnico. La página de inicio incluye además un formulario de consulta rápida de reparación y un enlace directo a la solicitud de reparación.

**Navegación privada (técnico autenticado)**

La barra de navegación privada incluye: Dashboard, Clientes, Reparaciones, Inventario, Calendario, Búsqueda global y el menú de usuario con opción de cerrar sesión.

**Navegación privada (administrador autenticado)**

El administrador dispone de todos los elementos del técnico más un menú desplegable de Administración que incluye: Usuarios, Solicitudes Web y Auditoría.

---

## 3.7 Conclusión del análisis

El análisis del sistema muestra que AndroTech es una aplicación de complejidad media-alta para el nivel del ciclo formativo, con tres tipos de usuarios diferenciados, 12 entidades de datos relacionadas y más de 40 rutas en el servidor. La correcta identificación de los requisitos desde el inicio del proyecto ha permitido construir un sistema coherente y completo, aunque con algunas funcionalidades que no estaban previstas en el anteproyecto inicial y que se fueron incorporando a medida que avanzaba el desarrollo.

---

---

# 4. DISEÑO

## 4.1 Introducción

El capítulo de diseño describe las decisiones técnicas tomadas para implementar los requisitos identificados en el análisis. Se detallan el entorno de desarrollo seleccionado, la base de datos, la arquitectura de la aplicación y la estructura de los módulos principales.

---

## 4.1.1 Selección del entorno de desarrollo

El entorno de desarrollo utilizado en el proyecto está compuesto por las siguientes herramientas. Visual Studio Code ha sido el editor principal, con las extensiones Python, Pylance y GitLens instaladas. Python 3.12 es el intérprete del lenguaje utilizado. Git y GitHub han sido las herramientas de control de versiones, con un repositorio público en github.com/manuelcortes07/Androtech que contiene todo el historial de commits del desarrollo. El sistema operativo utilizado ha sido Windows 11 Pro.

La selección de Visual Studio Code como editor responde a su gratuidad, su amplio soporte para Python y su integración nativa con Git, que ha permitido gestionar el control de versiones directamente desde el editor.

---

## 4.1.2 Selección de base de datos

Se ha seleccionado SQLite como sistema de base de datos por las siguientes razones. No requiere instalación de un servidor separado, ya que toda la base de datos se almacena en un único fichero. Es el sistema de base de datos incluido por defecto en Python a través del módulo `sqlite3`, sin necesidad de instalar dependencias adicionales. Es suficientemente robusto para el volumen de datos y el número de usuarios concurrentes esperado en un taller pequeño. Facilita enormemente el despliegue, ya que no requiere configurar credenciales de acceso a un servidor de base de datos.

La base de datos se almacena en `database/andro_tech.db` y su esquema completo es reproducible en cualquier momento ejecutando el script `create_db.py`.

---

## 4.2 Configuración de la plataforma

La aplicación Flask se configura en `app.py` mediante las siguientes variables de entorno cargadas desde el fichero `.env` con la librería `python-dotenv`. La variable `SECRET_KEY` es la clave secreta para la firma de las sesiones y los tokens CSRF. La variable `STRIPE_PUBLIC_KEY` es la clave pública de Stripe para el frontend. La variable `STRIPE_SECRET_KEY` es la clave secreta de Stripe para las llamadas a la API. La variable `STRIPE_WEBHOOK_SECRET` es el secreto para la validación de la firma del webhook. Las variables `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME` y `MAIL_PASSWORD` configuran el servidor SMTP para el envío de correos.

La aplicación se ejecuta en modo debug durante el desarrollo y debe ejecutarse con un servidor WSGI como Gunicorn en producción.

---

## 4.3 Capas de la aplicación

La arquitectura de AndroTech sigue un patrón de tres capas, adaptado a las características de Flask.

**Capa de presentación**

La capa de presentación está compuesta por los 38 templates Jinja2 ubicados en la carpeta `templates/`. Se utiliza Bootstrap 5.3 como framework CSS base, complementado con un fichero de estilos propio en `static/css/style.css` que define la identidad visual del sistema con la paleta de colores corporativa del taller (azul #2B8AC4 como color principal). Para las páginas públicas se utilizan librerías adicionales cargadas desde CDN: ScrollReveal para animaciones de entrada, Chart.js para los gráficos del dashboard, FullCalendar para el calendario de citas y Signature Pad para la firma digital.

**Capa de lógica de negocio**

La lógica de negocio se implementa principalmente en `app.py`, que contiene las 41 rutas de la aplicación, y en los módulos auxiliares. El módulo `auth.py` implementa los decoradores de autenticación y el sistema de roles y permisos. El módulo `audit.py` implementa el registro de eventos de auditoría. El módulo `alerts.py` implementa el cálculo de alertas inteligentes. El módulo `historial.py` implementa el registro de cambios de estado. La carpeta `utils/` contiene los servicios de email (`email_service.py`), generación de PDF (`pdf_generator.py`) y validaciones de seguridad (`security.py`).

**Capa de datos**

La capa de datos está implementada en `db.py`, que centraliza la gestión de la conexión a la base de datos SQLite. Todas las consultas se realizan mediante SQL directo con la librería `sqlite3` de Python, sin utilizar ningún ORM. Esta decisión, aunque implica escribir más código, proporciona un control total sobre las consultas y un mejor aprendizaje de SQL.

---

## 4.4 Estructura de la base de datos

La base de datos de AndroTech está compuesta por 12 tablas cuyo esquema SQL completo se muestra a continuación.

```sql
CREATE TABLE clientes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT NOT NULL,
    telefono    TEXT,
    email       TEXT,
    direccion   TEXT
);

CREATE TABLE reparaciones (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id      INTEGER,
    dispositivo     TEXT NOT NULL,
    descripcion     TEXT,
    estado          TEXT DEFAULT 'Pendiente',
    fecha_entrada   TEXT,
    fecha_salida    TEXT,
    precio          REAL,
    tipo_documento  TEXT DEFAULT 'presupuesto',
    estado_pago     TEXT DEFAULT 'Pendiente',
    fecha_pago      TEXT,
    metodo_pago     TEXT,
    firma           TEXT,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);

CREATE TABLE usuarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario     TEXT NOT NULL UNIQUE,
    contraseña  TEXT NOT NULL,
    rol         TEXT DEFAULT 'tecnico'
);

CREATE TABLE fotos_reparacion (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reparacion_id   INTEGER NOT NULL,
    filename        TEXT NOT NULL,
    descripcion     TEXT,
    fecha_subida    TEXT NOT NULL,
    subido_por      TEXT,
    FOREIGN KEY (reparacion_id) REFERENCES reparaciones(id) ON DELETE CASCADE
);

CREATE TABLE notas_reparacion (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reparacion_id   INTEGER NOT NULL,
    usuario         TEXT NOT NULL,
    contenido       TEXT NOT NULL,
    fecha_creacion  TEXT NOT NULL,
    es_importante   INTEGER DEFAULT 0,
    FOREIGN KEY (reparacion_id) REFERENCES reparaciones(id) ON DELETE CASCADE
);

CREATE TABLE inventario_piezas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre              TEXT NOT NULL,
    categoria           TEXT DEFAULT 'General',
    descripcion         TEXT,
    cantidad            INTEGER DEFAULT 0,
    cantidad_minima     INTEGER DEFAULT 5,
    precio_coste        REAL DEFAULT 0,
    precio_venta        REAL DEFAULT 0,
    proveedor           TEXT,
    ubicacion           TEXT,
    fecha_actualizacion TEXT
);

CREATE TABLE piezas_reparacion (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reparacion_id   INTEGER NOT NULL,
    pieza_id        INTEGER NOT NULL,
    cantidad        INTEGER DEFAULT 1,
    fecha_uso       TEXT NOT NULL,
    usuario         TEXT,
    FOREIGN KEY (reparacion_id) REFERENCES reparaciones(id),
    FOREIGN KEY (pieza_id) REFERENCES inventario_piezas(id)
);

CREATE TABLE solicitudes_reparacion (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre              TEXT NOT NULL,
    telefono            TEXT NOT NULL,
    email               TEXT,
    dispositivo         TEXT NOT NULL,
    marca               TEXT,
    modelo              TEXT,
    descripcion         TEXT NOT NULL,
    urgencia            TEXT DEFAULT 'normal',
    fecha_preferida     TEXT,
    horario_preferido   TEXT,
    estado              TEXT DEFAULT 'pendiente',
    notas_admin         TEXT,
    fecha_solicitud     TEXT NOT NULL,
    fecha_gestion       TEXT
);

CREATE TABLE reparaciones_historial (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    reparacion_id       INTEGER NOT NULL,
    estado_anterior     TEXT,
    estado_nuevo        TEXT NOT NULL,
    fecha_cambio        TEXT NOT NULL,
    usuario             TEXT
);

CREATE TABLE roles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT UNIQUE NOT NULL,
    descripcion TEXT,
    es_sistema  INTEGER DEFAULT 0,
    color       TEXT DEFAULT '#6c757d'
);

CREATE TABLE permisos_rol (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rol_nombre  TEXT NOT NULL,
    permiso     TEXT NOT NULL,
    UNIQUE(rol_nombre, permiso)
);

CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    usuario         TEXT,
    evento_datos    TEXT,
    ip_address      TEXT,
    timestamp       TEXT NOT NULL,
    UNIQUE(event_type, usuario, timestamp)
);

CREATE INDEX idx_audit_timestamp ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_event_type ON audit_log(event_type);
```

---

## 4.5 Arquitectura de la aplicación

La aplicación sigue una arquitectura monolítica típica de Flask, con las siguientes características estructurales.

El punto de entrada es `app.py`, que inicializa la aplicación Flask, carga la configuración desde las variables de entorno, registra los middlewares de seguridad, define las 41 rutas y arranca el servidor. Las rutas están agrupadas funcionalmente: rutas públicas, rutas de autenticación, rutas de clientes, rutas de reparaciones, rutas de administración, rutas de Stripe y rutas de API interna.

El sistema de autenticación implementado en `auth.py` utiliza el decorador `@login_required` para proteger las rutas que requieren autenticación y el decorador `@role_required` para las rutas que requieren un permiso específico. Los permisos se verifican consultando la tabla `permisos_rol` en cada petición.

El sistema CSRF implementado en `utils/security.py` genera un token único por sesión almacenado en la cookie de sesión de Flask. Todos los formularios incluyen un campo oculto con el token, que se valida en el servidor antes de procesar cualquier petición POST.

La integración con Stripe funciona mediante dos componentes. El primero es la ruta `/publico/pagar/<id>`, que crea una sesión de checkout en Stripe con los metadatos de la reparación y redirige al cliente a la página de pago de Stripe. El segundo es la ruta `/stripe/webhook`, que recibe las notificaciones de Stripe cuando se completa un pago, valida la firma criptográfica del webhook para garantizar que la petición proviene realmente de Stripe, y actualiza el estado de pago de la reparación en la base de datos.

El sistema de emails implementado en `utils/email_service.py` utiliza Flask-Mail para el envío de correos SMTP. Los correos se generan a partir de plantillas HTML Jinja2 almacenadas en `templates/emails/` y se envían en dos situaciones: cuando cambia el estado de una reparación, y cuando se confirma el pago mediante el webhook de Stripe.

La generación de PDF implementada en `utils/pdf_generator.py` utiliza la librería ReportLab para crear documentos PDF con diseño profesional. Los documentos incluyen el logo del taller, los datos del cliente y la reparación, el desglose del precio con IVA al 21%, los términos y condiciones y un código QR con el identificador de la reparación.
