# 5. IMPLEMENTACIÓN

## 5.1 Introducción

El capítulo de implementación describe cómo se ha llevado a la práctica el diseño definido en el capítulo anterior. Se detallan las decisiones de codificación más relevantes, los patrones utilizados y las herramientas de apoyo integradas en el sistema.

El desarrollo se realizó de forma incremental a lo largo de seis meses, comenzando por el núcleo básico del sistema y añadiendo funcionalidades progresivamente. Todo el historial de cambios está disponible en el repositorio público de GitHub: github.com/manuelcortes07/Androtech, donde los commits documentan la evolución del proyecto desde octubre de 2025 hasta abril de 2026.

---

## 5.2 Codificación de las capas principales

### 5.2.1 Inicialización y configuración de la aplicación

La aplicación se inicializa en `app.py`, que actúa como punto de entrada único del sistema. La configuración se carga desde el fichero `.env` mediante `python-dotenv`, garantizando que ninguna credencial sensible está incluida en el código fuente. La clave secreta de Flask se genera aleatoriamente en tiempo de ejecución si no está definida en las variables de entorno, como medida de seguridad adicional.

### 5.2.2 Sistema de seguridad CSRF

Se ha implementado un sistema de protección CSRF propio desde cero, sin depender de librerías externas, lo que ha permitido comprender en profundidad el mecanismo de este tipo de ataque y su mitigación.

El flujo completo de protección CSRF funciona de la siguiente manera. Cuando el usuario realiza la primera petición a cualquier ruta, el hook `before_request` ejecuta la función `ensure_csrf_token`, que genera un token aleatorio de 16 bytes codificado en base64url y lo almacena en la sesión de Flask si no existía previamente. Este token se inyecta automáticamente en todos los templates Jinja2 mediante un context processor, de forma que cada formulario puede incluirlo en un campo oculto sin necesidad de pasarlo manualmente desde cada ruta. Cuando el usuario envía un formulario, el decorador `@csrf_protect` compara el token recibido en el cuerpo de la petición POST con el token almacenado en la sesión. Si no coinciden, la petición se rechaza con un mensaje de error y se redirige al usuario a la misma página.

```python
# Generación del token (utils/security.py)
def ensure_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(16)

# Validación en rutas protegidas (utils/security.py)
def validate_csrf():
    token = request.form.get('csrf_token', '')
    if not token or token != session.get('csrf_token'):
        flash('Formulario inválido o expirado. Intenta de nuevo.', 'danger')
        return False
    return True
```

Este sistema protege contra ataques de tipo Cross-Site Request Forgery, donde un sitio web malicioso podría intentar enviar peticiones en nombre de un usuario autenticado sin su conocimiento.

### 5.2.3 Sistema de autenticación y roles

El sistema de autenticación utiliza sesiones de Flask para mantener el estado del usuario entre peticiones. Las contraseñas se almacenan hasheadas con el algoritmo de Werkzeug, que utiliza internamente PBKDF2 con SHA-256, garantizando que incluso si la base de datos fuera comprometida, las contraseñas originales no serían recuperables.

El sistema de roles implementa 31 permisos granulares organizados en cinco categorías: gestión de clientes, gestión de reparaciones, funciones de administración, gestión de inventario y configuración del sistema. Cada ruta sensible está protegida con el decorador `@role_required`, que verifica si el rol del usuario tiene el permiso necesario antes de ejecutar la función.

### 5.2.4 Rate limiting en el login

Para proteger el sistema contra ataques de fuerza bruta, se ha integrado Flask-Limiter con una restricción de cinco peticiones POST por minuto por dirección IP en la ruta de login. Cuando se supera este límite, el sistema devuelve un mensaje en español al usuario y redirige a la página de login. El almacenamiento del contador de peticiones se realiza en memoria, lo que es adecuado para un entorno de servidor único.

### 5.2.5 Gestión de la base de datos

Todas las operaciones con la base de datos utilizan el módulo `sqlite3` de Python con consultas parametrizadas, lo que previene ataques de inyección SQL. La conexión se gestiona de forma centralizada en `db.py`, garantizando que cada petición abre y cierra correctamente su conexión a la base de datos.

Las claves foráneas están habilitadas explícitamente en cada conexión mediante el comando `PRAGMA foreign_keys = ON`, garantizando la integridad referencial entre tablas. La tabla `audit_log` dispone de dos índices adicionales sobre los campos `timestamp` y `event_type` para optimizar las consultas de búsqueda en el log de auditoría.

### 5.2.6 Sistema de estados y transiciones

El sistema de estados de las reparaciones implementa un flujo controlado que impide transiciones inválidas. Los estados disponibles son Pendiente, En Proceso, Terminado y Entregado. Las transiciones permitidas están definidas en `app.py` y se validan en el servidor antes de aplicar cualquier cambio. Un técnico no puede, por ejemplo, devolver una reparación marcada como Entregado al estado Pendiente. Cada cambio de estado queda registrado automáticamente en la tabla `reparaciones_historial` con el estado anterior, el nuevo estado, la fecha y el usuario que realizó el cambio.

### 5.2.7 Integración con Stripe

La integración de pagos con Stripe se implementa mediante dos componentes. El primero es la creación de sesiones de checkout: cuando el cliente accede al enlace de pago de su reparación, el servidor realiza una llamada a la API de Stripe para crear una sesión de pago con el importe de la reparación, los metadatos necesarios (identificador de reparación y email del cliente) y las URLs de redirección en caso de éxito o cancelación. El segundo componente es el webhook de confirmación: Stripe envía una notificación al endpoint `/stripe/webhook` cuando el pago se completa. El servidor valida criptográficamente la firma del webhook para garantizar que la petición proviene de Stripe y no de un tercero, y actualiza el estado de pago de la reparación en la base de datos.

### 5.2.8 Generación de PDF

Los documentos PDF se generan con la librería ReportLab mediante la clase `InvoiceGenerator` implementada en `utils/pdf_generator.py`. El sistema soporta dos tipos de documentos: presupuesto y factura. Ambos incluyen el logo del taller, los datos completos del cliente y la reparación, el importe con el IVA al 21% desglosado, los términos y condiciones del servicio y un código QR con el identificador de la reparación que permite verificar la autenticidad del documento.

### 5.2.9 Sistema de emails automáticos

El servicio de email implementado en `utils/email_service.py` utiliza Flask-Mail para el envío de correos SMTP. El sistema dispone de cinco plantillas HTML profesionales almacenadas en `templates/emails/`. Los emails se envían en dos situaciones: cuando el técnico actualiza el estado de una reparación, y cuando el webhook de Stripe confirma el pago. El sistema está diseñado para no interrumpir el funcionamiento de la aplicación si el servicio SMTP no está configurado o falla, registrando el error en el log del sistema.

### 5.2.10 Sistema de auditoría

El módulo `audit.py` implementa un sistema de registro de eventos críticos que almacena en la tabla `audit_log` información estructurada en formato JSON sobre cada acción relevante del sistema: inicio de sesión, cambios de estado, pagos, creación o eliminación de registros. Cada entrada incluye el tipo de evento, el usuario que lo realizó, los datos del evento, la dirección IP del cliente y el timestamp. El log también se escribe en fichero con rotación automática cada 5 MB, manteniendo los últimos tres ficheros de backup.

---

## 5.3 Integración de las herramientas de apoyo

### Chart.js

Los gráficos del dashboard se implementan con Chart.js cargado desde CDN. El servidor calcula los datos necesarios (ingresos por mes, reparaciones por técnico, distribución de estados, dispositivos más reparados) en la ruta del dashboard y los pasa al template Jinja2 serializado como JSON, donde Chart.js los renderiza en elementos canvas HTML5.

### FullCalendar

El calendario de citas integra la librería FullCalendar cargada desde CDN. Las citas se almacenan en la base de datos y se sirven al frontend mediante una ruta de API interna que devuelve los eventos en formato JSON compatible con FullCalendar.

### ScrollReveal

Las animaciones de entrada de la página pública utilizan ScrollReveal, que aplica efectos de aparición progresiva a los elementos a medida que el usuario hace scroll. Esta librería se carga desde CDN y se inicializa con una configuración de fade-in con desplazamiento vertical.

### Signature Pad

La firma digital del cliente se implementa con la librería Signature Pad, que renderiza un canvas HTML5 donde el cliente puede firmar con el ratón o con el dedo en dispositivos táctiles. La firma se serializa como imagen en formato base64 y se almacena en el campo `firma` de la tabla `reparaciones`.

### PWA (Progressive Web App)

La aplicación está configurada como PWA mediante un service worker y un fichero `manifest.json`. Esto permite que los usuarios instalen la aplicación en su dispositivo móvil como si fuera una app nativa, con icono en el escritorio y funcionamiento básico sin conexión a internet.

---

---

# 6. PRUEBAS

## 6.1 Introducción

Las pruebas del sistema tienen como objetivo verificar que todas las funcionalidades implementadas funcionan correctamente y que el sistema se comporta de forma adecuada tanto en los escenarios normales de uso como ante entradas incorrectas o situaciones de error.

Las pruebas se han realizado de forma manual a lo largo de todo el desarrollo, probando cada funcionalidad inmediatamente después de su implementación. Además, se han realizado pruebas de integración para verificar que los diferentes módulos del sistema funcionan correctamente en conjunto.

---

## 6.2 Pruebas realizadas

### 6.2.1 Pruebas de autenticación y seguridad

**Prueba 1: Login con credenciales correctas**
Se accede a la ruta `/login` con usuario y contraseña correctos. El sistema redirige al dashboard y la sesión queda establecida correctamente.

**Prueba 2: Login con credenciales incorrectas**
Se accede a la ruta `/login` con contraseña incorrecta. El sistema muestra un mensaje de error y no establece sesión.

**Prueba 3: Rate limiting en login**
Se realizan seis peticiones POST consecutivas a `/login` desde la misma IP en menos de un minuto. El sexto intento devuelve un mensaje de error indicando que se ha superado el límite y redirige al login. Los intentos anteriores funcionan con normalidad.

**Prueba 4: Protección CSRF**
Se intenta enviar un formulario POST sin el token CSRF o con un token inválido. El sistema rechaza la petición, muestra el mensaje "Formulario inválido o expirado" y redirige al usuario a la misma página.

**Prueba 5: Acceso sin autenticación a rutas privadas**
Se intenta acceder a `/dashboard`, `/clientes` y `/reparaciones` sin estar autenticado. El sistema redirige al login en todos los casos.

**Prueba 6: Acceso a rutas de administrador con cuenta de técnico**
Se intenta acceder a `/admin/usuarios` con una cuenta de rol técnico. El sistema deniega el acceso y muestra un mensaje de permiso insuficiente.

### 6.2.2 Pruebas de gestión de clientes y reparaciones

**Prueba 7: Creación de cliente**
Se crea un cliente nuevo con todos los campos obligatorios y opcionales. El cliente aparece en el listado y sus datos son correctos.

**Prueba 8: Creación de reparación**
Se crea una reparación asociada a un cliente existente. La reparación aparece en el listado con estado "Pendiente" y la fecha de entrada correcta.

**Prueba 9: Cambio de estado de reparación**
Se cambia el estado de una reparación de "Pendiente" a "En Proceso". El cambio queda reflejado en el listado y en el historial de la reparación con el usuario y la fecha del cambio.

**Prueba 10: Transición de estado inválida**
Se intenta cambiar el estado de una reparación con estado "Entregado" a "Pendiente". El sistema bloquea la operación y muestra un mensaje de error.

**Prueba 11: Consulta pública de reparación**
Se accede a `/consulta` e introduce un número de reparación existente con el email correcto del cliente. El sistema muestra los datos de la reparación correctamente.

**Prueba 12: Consulta pública con email incorrecto**
Se introduce un número de reparación existente con un email que no corresponde al cliente. El sistema muestra un mensaje de error y no revela ningún dato de la reparación.

### 6.2.3 Pruebas de pagos con Stripe

**Prueba 13: Pago online en entorno de pruebas**
Se accede al enlace de pago de una reparación en estado "Terminado". El sistema redirige al checkout de Stripe. Se introduce la tarjeta de prueba 4242 4242 4242 4242. Stripe confirma el pago, el webhook actualiza la reparación como pagada y el cliente recibe el email de confirmación.

**Prueba 14: Intento de pago de reparación ya pagada**
Se intenta acceder al enlace de pago de una reparación que ya tiene estado de pago "Completado". El sistema bloquea el intento y muestra un mensaje indicando que ya fue pagada.

**Prueba 15: Intento de pago de reparación no terminada**
Se intenta acceder al enlace de pago de una reparación con estado "En Proceso". El sistema bloquea el intento y muestra un mensaje indicando que la reparación no está lista.

### 6.2.4 Pruebas de generación de PDF

**Prueba 16: Generación de presupuesto**
Se genera el PDF de presupuesto de una reparación. El documento se descarga correctamente y contiene todos los datos esperados: datos del taller, datos del cliente, descripción de la reparación, precio sin IVA, IVA al 21%, total y código QR.

**Prueba 17: Generación de factura**
Se genera el PDF de factura de una reparación pagada. El documento incluye el número de factura, la fecha de pago y el método de pago utilizado.

### 6.2.5 Pruebas de emails automáticos

**Prueba 18: Email de cambio de estado**
Se cambia el estado de una reparación cuyo cliente tiene email registrado. El cliente recibe un email con la plantilla de actualización de estado, con el nuevo estado y los datos de la reparación.

**Prueba 19: Email de confirmación de pago**
Se completa el pago de una reparación mediante Stripe en entorno de pruebas. El cliente recibe un email de confirmación con el detalle de la reparación y el importe pagado.

### 6.2.6 Pruebas del dashboard

**Prueba 20: KPIs en tiempo real**
Se crea un nuevo cliente y una nueva reparación. Los contadores del dashboard se actualizan correctamente en la siguiente carga de la página.

**Prueba 21: Exportación CSV**
Se exporta el listado de reparaciones a CSV. El fichero se descarga correctamente y se abre sin errores en Microsoft Excel, con el separador de punto y coma y codificación UTF-8 con BOM.

---

## 6.3 Resultados obtenidos

Todas las pruebas descritas han producido los resultados esperados. Los únicos incidentes relevantes detectados durante el desarrollo y ya corregidos son los siguientes.

Durante el desarrollo inicial se detectó que el fichero `requirements.txt` se había guardado con codificación UTF-16 en lugar de UTF-8, lo que impedía su lectura por parte de `pip`. Se corrigió reescribiendo el fichero con la codificación correcta.

Se detectó la inclusión accidental de una clave de API de Stripe en un script de prueba durante el desarrollo. GitHub bloqueó automáticamente el push mediante su sistema de protección de secretos. La clave fue revocada inmediatamente desde el panel de Stripe y el historial de commits fue limpiado.

Se detectaron mensajes de depuración con datos sensibles (direcciones de email, identificadores de reparación) en el módulo `utils/email_service.py`. Estos mensajes fueron eliminados y sustituidos por el sistema de logging estructurado JSON ya existente en el proyecto.

---

## 6.4 Conclusiones

El sistema supera satisfactoriamente todas las pruebas funcionales y de seguridad realizadas. Las funcionalidades críticas del sistema, incluyendo la gestión de reparaciones, los pagos con Stripe, la consulta pública y la generación de PDF, funcionan correctamente en todos los escenarios probados, incluyendo los casos de uso erróneos.

Las medidas de seguridad implementadas (CSRF, rate limiting, validación de webhook, roles y permisos) han demostrado su efectividad en las pruebas específicas diseñadas para cada una.

---

---

# 7. CONCLUSIONES

## 7.1 Conclusiones finales

El proyecto AndroTech ha cumplido con creces los objetivos definidos en el anteproyecto inicial. Se ha desarrollado una aplicación web completa, funcional y segura que digitaliza la gestión integral de un taller técnico de reparaciones, superando el alcance original en múltiples aspectos.

El sistema entregado incluye todas las funcionalidades comprometidas en el anteproyecto (gestión de clientes y reparaciones, sistema de estados, consulta pública, generación de PDF y panel de administración) más un conjunto significativo de funcionalidades adicionales no previstas inicialmente: integración de pagos online con Stripe, comunicación automática por email con cinco plantillas HTML, sistema de roles con 31 permisos granulares, inventario de piezas, calendario de citas, firma digital, fotos de reparación, búsqueda global, auditoría completa, rate limiting, Progressive Web App y un rediseño visual completo de todas las páginas públicas.

Desde el punto de vista técnico, el proyecto ha demostrado que es posible construir una aplicación de gestión empresarial completa con tecnologías de código abierto y coste cero en términos de licencias de software. Flask ha demostrado ser una elección adecuada para este tipo de proyectos, proporcionando la flexibilidad necesaria para implementar cada componente con comprensión real de su funcionamiento.

Desde el punto de vista formativo, el proyecto ha permitido aplicar de forma práctica e integrada los conocimientos adquiridos en los módulos del ciclo formativo, especialmente en las áreas de desarrollo web, bases de datos, seguridad informática y servicios en red.

## 7.2 Desviaciones temporales

La planificación inicial estimaba una dedicación de 60 a 80 horas para el desarrollo completo del proyecto. La dedicación real ha sido significativamente superior, estimada en torno a las 160 horas, distribuidas a lo largo de seis meses. Esta desviación se explica principalmente por tres factores.

El primero es el aprendizaje desde cero de tecnologías no conocidas previamente, especialmente la integración con la API de Stripe, el sistema de webhooks, la generación de PDF con ReportLab y la configuración del servicio SMTP con Flask-Mail. Cada una de estas integraciones requirió un período de estudio y prueba antes de poder implementarse correctamente.

El segundo factor es la incorporación de funcionalidades adicionales no previstas en el anteproyecto, como el sistema de roles granular, la firma digital, el inventario de piezas y la PWA, que surgieron como mejoras naturales durante el desarrollo.

El tercer factor es el tiempo dedicado al rediseño visual completo de las páginas públicas, realizado en la fase final del proyecto para mejorar la presentación y diferenciarse del aspecto genérico de las plantillas Bootstrap estándar.

## 7.3 Posibles ampliaciones y modificaciones

El sistema actual es funcional y completo para las necesidades del taller, pero existen varias líneas de ampliación que podrían implementarse en el futuro.

La primera ampliación prioritaria sería la migración de SQLite a PostgreSQL para mejorar la robustez y la capacidad de acceso concurrente, preparando el sistema para un posible crecimiento del negocio.

La segunda ampliación sería la implementación de notificaciones por WhatsApp mediante la API de Twilio, complementando el sistema de emails existente con un canal de comunicación más inmediato y con mayor tasa de lectura.

La tercera ampliación sería el desarrollo de una API REST con Flask-RESTful que permitiera integrar el sistema con aplicaciones móviles nativas o con otros sistemas de gestión del taller.

La cuarta ampliación sería la implementación de autenticación de dos factores (2FA) en el login mediante TOTP (Time-based One-Time Password) con la librería pyotp, añadiendo una capa adicional de seguridad al acceso al panel de administración.

La quinta ampliación sería la configuración de copias de seguridad automáticas de la base de datos en la nube mediante Amazon S3 o Google Cloud Storage, eliminando el riesgo de pérdida de datos por fallo del servidor.

## 7.4 Valoración personal

El desarrollo de AndroTech ha sido la experiencia de aprendizaje más intensa y completa de mi etapa en el ciclo formativo. Comenzar el proyecto en octubre de 2025 con conocimientos básicos de Python y HTML, y entregar en abril de 2026 un sistema con integración de pagos, emails automáticos, firma digital y más de cuarenta rutas, ha supuesto un esfuerzo considerable que valoro muy positivamente.

Lo más importante que me llevo del proyecto no es el código en sí, sino la capacidad de enfrentarme a un problema complejo, dividirlo en partes manejables, buscar la información necesaria para resolverlo y persistir hasta encontrar la solución. Cada funcionalidad que no funcionaba al principio y que terminé haciendo funcionar ha reforzado esa capacidad.

También ha sido muy valioso desarrollar el proyecto sobre una necesidad real de un negocio existente en Huelva. Saber que el sistema podría ser utilizado de verdad ha sido una motivación constante durante los momentos más difíciles del desarrollo.

---

---

# 8. BIBLIOGRAFÍA

- Flask. (2024). *Flask documentation (3.x)*. Pallets Projects. https://flask.palletsprojects.com
- Stripe. (2024). *Stripe API reference and documentation*. Stripe Inc. https://stripe.com/docs
- Bootstrap. (2023). *Bootstrap 5.3 documentation*. The Bootstrap Authors. https://getbootstrap.com/docs/5.3
- ReportLab. (2023). *ReportLab PDF library user guide*. ReportLab Inc. https://www.reportlab.com/docs/reportlab-userguide.pdf
- Flask-Mail. (2023). *Flask-Mail documentation*. https://flask-mail.readthedocs.io
- Flask-Limiter. (2024). *Flask-Limiter documentation*. https://flask-limiter.readthedocs.io
- Python Software Foundation. (2024). *Python 3.12 documentation — sqlite3*. https://docs.python.org/3/library/sqlite3.html
- Python Software Foundation. (2024). *Python 3.12 documentation — secrets*. https://docs.python.org/3/library/secrets.html
- Werkzeug. (2024). *Werkzeug documentation — security helpers*. Pallets Projects. https://werkzeug.palletsprojects.com/en/3.x/utils/#werkzeug.security.generate_password_hash
- OWASP. (2023). *OWASP Cross-Site Request Forgery (CSRF) prevention cheat sheet*. https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP. (2023). *OWASP Authentication cheat sheet*. https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- Mozilla Developer Network. (2024). *HTTP security headers*. https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers
- Chart.js. (2023). *Chart.js documentation*. https://www.chartjs.org/docs
- FullCalendar. (2023). *FullCalendar documentation*. https://fullcalendar.io/docs
- Jinja. (2024). *Jinja2 template designer documentation*. Pallets Projects. https://jinja.palletsprojects.com
- Agencia Española de Protección de Datos. (2018). *Reglamento General de Protección de Datos (RGPD)*. https://www.aepd.es/reglamento-general-proteccion-datos
- Boletín Oficial del Estado. (2018). *Ley Orgánica 3/2018, de 5 de diciembre, de Protección de Datos Personales y garantía de los derechos digitales*. https://www.boe.es/eli/es/lo/2018/12/05/3
- PCI Security Standards Council. (2022). *PCI DSS v4.0*. https://www.pcisecuritystandards.org

---

---

# 9. GLOSARIO

**API (Application Programming Interface):** Conjunto de reglas y protocolos que permite a diferentes aplicaciones comunicarse entre sí. En AndroTech se utiliza la API de Stripe para la gestión de pagos.

**Bootstrap:** Framework CSS de código abierto que facilita el desarrollo de interfaces web responsivas y adaptadas a diferentes tamaños de pantalla.

**CSRF (Cross-Site Request Forgery):** Tipo de ataque web en el que un sitio malicioso engaña al navegador del usuario para que envíe peticiones no autorizadas a una aplicación en la que el usuario está autenticado. AndroTech implementa protección contra este tipo de ataque mediante tokens de validación.

**CRUD:** Acrónimo de Create, Read, Update, Delete. Hace referencia a las cuatro operaciones básicas que se pueden realizar sobre los datos de una base de datos.

**Dashboard:** Panel de control visual que muestra en una sola pantalla los indicadores clave de rendimiento (KPIs) de un sistema o negocio.

**Flask:** Microframework de Python para el desarrollo de aplicaciones web. Se denomina "micro" porque no impone una estructura fija ni incluye componentes como ORM o sistema de autenticación, dejando esas decisiones al desarrollador.

**Hash:** Resultado de aplicar una función matemática unidireccional a un dato. En seguridad informática, las contraseñas se almacenan como hash para que no sea posible recuperar la contraseña original aunque se acceda a la base de datos.

**IVA (Impuesto sobre el Valor Añadido):** Impuesto indirecto sobre el consumo. En España, el tipo general es el 21%, que se aplica a los servicios de reparación de dispositivos electrónicos.

**Jinja2:** Motor de plantillas para Python utilizado por Flask. Permite generar HTML dinámico combinando código Python con marcado HTML mediante una sintaxis especial con llaves dobles y llaves con porcentaje.

**JSON (JavaScript Object Notation):** Formato ligero de intercambio de datos, fácil de leer y escribir para personas y de analizar y generar para máquinas. AndroTech lo utiliza para el log de auditoría y para la comunicación entre el servidor y las librerías JavaScript del frontend.

**KPI (Key Performance Indicator):** Indicador clave de rendimiento. Métrica que permite evaluar el rendimiento de un proceso o actividad. En AndroTech se utilizan KPIs como el número de reparaciones activas, los ingresos del mes o la tasa de cobro.

**Middleware:** Software que actúa como intermediario entre el servidor y la aplicación, procesando las peticiones antes de que lleguen a las rutas. En AndroTech se utilizan middlewares para la generación del token CSRF y los headers de seguridad HTTP.

**PDF (Portable Document Format):** Formato de archivo desarrollado por Adobe que permite representar documentos de forma independiente del hardware y software en que fueron creados.

**PWA (Progressive Web App):** Tipo de aplicación web que utiliza tecnologías modernas para ofrecer una experiencia similar a la de una aplicación nativa, incluyendo la posibilidad de instalarse en el dispositivo y funcionar sin conexión.

**Rate Limiting:** Técnica de seguridad que limita el número de peticiones que un cliente puede realizar a un servidor en un período de tiempo determinado. Se utiliza para prevenir ataques de fuerza bruta y abuso de la API.

**ReportLab:** Librería de Python para la generación programática de documentos PDF. Permite crear documentos con texto, imágenes, tablas y gráficos con control total sobre el diseño.

**RGPD (Reglamento General de Protección de Datos):** Reglamento de la Unión Europea que establece las normas relativas a la protección de las personas físicas en lo que respecta al tratamiento de datos personales.

**SQLite:** Sistema de gestión de base de datos relacional contenido en una biblioteca de C. A diferencia de otros sistemas de base de datos, SQLite no requiere un proceso servidor separado, almacenando toda la base de datos en un único fichero.

**Stripe:** Plataforma de pagos online que permite a empresas y desarrolladores aceptar pagos por Internet de forma segura. Cumple con el estándar PCI DSS y gestiona el procesamiento de tarjetas bancarias.

**Token CSRF:** Valor aleatorio e impredecible generado por el servidor y asociado a la sesión del usuario. Se incluye en cada formulario y se verifica en el servidor para garantizar que la petición proviene de un formulario legítimo de la aplicación.

**Webhook:** Mecanismo que permite a una aplicación notificar a otra de forma automática cuando ocurre un evento, enviando una petición HTTP a una URL predefinida. AndroTech utiliza el webhook de Stripe para recibir la confirmación de los pagos.

**Werkzeug:** Librería de Python utilizada por Flask para el manejo de peticiones HTTP. Incluye utilidades de seguridad como las funciones de hash de contraseñas utilizadas en AndroTech.

**WSGI (Web Server Gateway Interface):** Especificación estándar de Python que define cómo un servidor web se comunica con una aplicación web Python. Flask es una aplicación WSGI que puede desplegarse con servidores como Gunicorn o uWSGI en producción.
