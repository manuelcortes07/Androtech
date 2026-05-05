# 📘 Guía de mi código — AndroTech

> Este documento lo he escrito para mí mismo. Es un mapa del proyecto que me
> permite llegar a la defensa del TFG sabiendo explicar **qué hace cada cosa**,
> **por qué está así** y **qué pasa por debajo cuando un cliente paga una
> reparación**. No contiene código entero: solo las partes clave con el
> contexto mínimo para entenderlas.

---

## 1. Los ficheros del proyecto, uno por uno

Estos son los ficheros principales que componen AndroTech. He dejado fuera
`venv/`, `__pycache__/` y los ficheros de entorno (`.env`, `requirements.txt`)
porque no contienen lógica de la aplicación.

### Código Python (la lógica)

- **`app.py`** — Es el cerebro de la aplicación. Un único fichero Flask con
  unas 4.000 líneas que define **todas las rutas** (login, reparaciones,
  clientes, inventario, pagos, admin…) y conecta todo lo demás. Cuando
  arrancas `python app.py` es este fichero el que se ejecuta.

- **`db.py`** — Lo más pequeño y simple. Solo abre la conexión SQLite al
  fichero `database/andro_tech.db` y configura `row_factory` para que las
  filas se comporten como diccionarios (así puedo hacer `fila["nombre"]`
  en vez de `fila[0]`).

- **`auth.py`** — El sistema de permisos. Define los 31 permisos disponibles
  (por ejemplo `reparaciones_crear`, `clientes_eliminar`), qué permisos
  tiene cada rol (admin o técnico), y los decoradores `@login_required` y
  `@permiso_requerido(...)` que uso en `app.py` para proteger rutas.

- **`historial.py`** — Gestiona el **cambio de estado** de una reparación
  (Pendiente → En proceso → Terminado → Entregado). Define qué transiciones
  son válidas para un técnico y registra cada cambio en
  `reparaciones_historial` para tener trazabilidad.

- **`audit.py`** — Guarda un registro de eventos críticos (logins, alta de
  reparaciones, pagos…) en la tabla `audit_log`. Es una pista de auditoría
  pensada para cumplir el requisito de poder reconstruir qué hizo cada
  usuario.

- **`alerts.py`** — Calcula las alertas del dashboard: piezas con stock bajo,
  reparaciones antiguas sin terminar, pagos pendientes, etc.

- **`utils/email_service.py`** — Envío de correos (confirmación de pago,
  cambio de estado, bienvenida, factura…). Usa `smtplib` y
  `email.message.EmailMessage` directamente en lugar de Flask-Mail porque
  Flask-Mail 0.10 tiene un bug de codificación con acentos y emojis.

- **`utils/pdf_generator.py`** — Genera los PDF de presupuesto y factura
  usando ReportLab. Incluye cabecera corporativa, datos del cliente, tabla
  de servicios con IVA al 21%, términos y condiciones y un **código QR**
  que lleva al cliente a consultar el estado.

- **`utils/security.py`** — Validaciones de seguridad: token CSRF (protección
  contra que un sitio externo te envíe formularios falsos), validador de
  contraseña fuerte y validador de precio positivo.

### Plantillas HTML (`templates/`)

- **`base.html`** — Layout común con navbar, footer y bloques Jinja. Todas
  las demás plantillas heredan de aquí.
- **`login.html`, `dashboard.html`, `index.html`** — Página de login, panel
  principal para el usuario autenticado y portada pública.
- **`reparaciones*.html`, `clientes*.html`, `inventario*.html`** — CRUD
  completo para cada entidad (listar, crear, editar, ver detalle).
- **`consulta.html`, `mis_reparaciones.html`** — Páginas públicas sin login
  donde el cliente consulta su reparación.
- **`emails/*.html`** — Plantillas HTML de los correos automáticos.
- **`admin_*.html`** — Paneles de administración (usuarios, sistema, auditoría,
  prueba de email).

### Ficheros estáticos (`static/`)

- **`style.css`** + variables de tema (modo claro/oscuro).
- **`logo_androtech.png`** y gráficos de la marca.
- **`defensa/`** — Presentación HTML y manual del TFG para la defensa.

### Configuración y despliegue

- **`Procfile`** — Dice a Railway cómo arrancar: Gunicorn con 2 workers y
  timeout de 120 s.
- **`requirements.txt`** — Lista de dependencias Python (Flask, Stripe,
  ReportLab, Pillow…).
- **`.env`** — Variables secretas (claves de Stripe, contraseña SMTP,
  SECRET_KEY). **No subido a Git** por seguridad.
- **`create_db.py`** — Script para crear la base de datos desde cero.

---

## 2. Las 10 funciones más importantes

He seleccionado las 10 que, si entiendes, entiendes el proyecto entero.

### 1. `login()` — `app.py`, línea 518
Recibe usuario y contraseña por formulario, busca al usuario en la tabla
`usuarios`, y comprueba la contraseña con `check_password_hash`. Si cuadra,
guarda en la sesión Flask `usuario`, `rol` y la lista de `permisos`. Está
protegida por `@limiter.limit("5 per minute")` para que un atacante no
pueda probar miles de contraseñas, y por `@csrf_protect` para evitar que
se envíen formularios desde otra web. **Por qué está aquí:** es la puerta
de entrada de todo el sistema.

### 2. `tiene_permiso(permiso)` — `auth.py`
Devuelve `True` si el usuario en sesión tiene ese permiso concreto. Si el
rol es `admin` siempre dice sí; si es `tecnico` mira la lista de permisos
cargada en la sesión al hacer login. **Por qué está aquí:** permite ocultar
o mostrar botones en las plantillas (`{% if tiene_permiso('...') %}`) sin
tener que repetir `if` gigantes.

### 3. `nueva_reparacion()` — `app.py`, línea 1564
Gestiona el alta de una reparación. En GET muestra el formulario; en POST
valida los datos, inserta en `reparaciones`, envía un email al cliente
con `send_nueva_reparacion`, y redirige al listado. Registra el evento en
`audit_log`. **Por qué está aquí:** es la operación de negocio más habitual
del taller.

### 4. `consulta()` — `app.py`, línea 2993
Página pública (sin login) donde el cliente introduce el número de su
reparación y ve el estado. Soporta también un parámetro `?id=5` en la URL,
que es lo que usa el código QR del PDF para entrar directamente. **Por qué
está aquí:** es la cara pública del taller, lo que ven los clientes.

### 5. `publico_pagar_reparacion(id)` — `app.py`, alrededor de línea 3720
Cuando el cliente pulsa "Pagar con tarjeta" en la consulta, esta función
valida que la reparación existe, no está ya pagada, tiene precio positivo
y el email que el cliente ha metido coincide con el del registro. Si todo
cuadra, crea una sesión de Stripe Checkout y redirige al cliente a la
página de pago de Stripe. **Por qué está aquí:** es el punto donde nuestro
sistema "entrega el control" a Stripe para cobrar de forma segura sin
tocar tarjetas.

### 6. `stripe_webhook()` — `app.py`, línea 3856
Stripe llama a esta URL después de que el cliente paga. Verifica la firma
del mensaje con `STRIPE_WEBHOOK_SECRET`, y si es un evento
`checkout.session.completed` marca la reparación como `Pagado`, guarda
fecha y método (`Tarjeta (Stripe)`), registra auditoría y envía email
de confirmación con la factura PDF adjunta. **Por qué está aquí:** es el
único punto donde podemos confiar en que el cobro se ha completado.

### 7. `generar_presupuesto_pdf(reparacion_data, tipo_documento, base_url)`
— `utils/pdf_generator.py`, línea 323
Construye un PDF completo en memoria (`BytesIO`) para descargar o adjuntar
al email. Monta cabecera con el logo, datos de cliente, dispositivo, tabla
de servicios con IVA, términos y condiciones, pie de página y un QR que
lleva a `/consulta?id=X`. **Por qué está aquí:** centraliza toda la parte
gráfica del documento para que solo haya una versión "bonita" del
presupuesto/factura.

### 8. `validar_transicion(estado_actual, estado_nuevo, rol)` — `historial.py`
Comprueba si un técnico puede pasar una reparación de un estado a otro.
Por ejemplo, un técnico **no** puede saltarse "Pendiente → Terminado"
directamente (tiene que pasar por "En proceso"); un admin sí puede. **Por
qué está aquí:** impide que un técnico despistado marque como terminada
una reparación que ni siquiera se ha empezado.

### 9. `validate_csrf()` / `csrf_protect` — `utils/security.py`
Genera un token aleatorio y único por sesión, lo mete en todos los
formularios (`{{ csrf_token }}`) y al enviar el formulario comprueba que
coincide. **Por qué está aquí:** sin esto, una web maliciosa podría
engañar al navegador de un admin logueado para borrar reparaciones
haciéndole clic en un botón oculto.

### 10. `EmailService._send(...)` — `utils/email_service.py`, línea 37
Envío de bajo nivel: toma la config SMTP (servidor, puerto, usuario,
contraseña, TLS/SSL), construye un `EmailMessage` con la cabecera y
cuerpo HTML codificados correctamente en UTF-8 (soporta acentos y
emojis), y lo envía vía `smtplib`. Los adjuntos (factura PDF) se pasan
como lista de tuplas. **Por qué está aquí:** es la capa que hace que
todos los emails de la app "simplemente funcionen" sin depender de
Flask-Mail.

---

## 3. Las 5 partes más complejas, explicadas

### A) Webhook de Stripe (`stripe_webhook`)
Cuando un cliente paga, Stripe no nos avisa en la misma petición: te
manda por detrás una llamada HTTP a `/stripe/webhook` con los datos del
evento. El problema es que cualquiera podría falsificar esa llamada y
marcar reparaciones como pagadas sin haber pagado. Por eso, antes de
tocar nada, llamamos a `stripe.Webhook.construct_event(payload,
sig_header, STRIPE_WEBHOOK_SECRET)`, que usa un secreto compartido para
verificar que el mensaje viene **realmente** de Stripe. Además comparamos
el importe pagado con el precio de la reparación (tolerancia de 0,01 €)
y comprobamos que no estaba ya pagada (idempotencia: si Stripe reintenta
mandar el mismo evento, no marcamos nada dos veces).

### B) Generación de PDF con QR (`generar_presupuesto_pdf`)
El PDF se construye con ReportLab en bloques (`_build_header`,
`_build_client_info`, `_build_services_table`, `_build_totals`…) que van
metiendo elementos en una lista `elements`; al final `doc.build(elements)`
los pega en un único fichero. Lo más sutil es el QR: creamos un
`QrCodeWidget` con la URL `/consulta?id=X`, pero la URL base no puede ser
fija — si uso `localhost:5000` funciona en mi máquina pero el QR impreso
no sirve en producción. Por eso la función recibe `base_url` desde la vista
Flask (`request.host_url`), que sabe si está corriendo en local o en
`https://androtech-production.up.railway.app`.

### C) Validación CSRF (`csrf_protect`)
CSRF = Cross-Site Request Forgery. El ataque es que un usuario logueado en
mi app abre otra web maliciosa, esa web incrusta un `<form>` que envía
POST a mi `/reparaciones/borrar/5`, y el navegador manda la cookie de
sesión automáticamente. La defensa es meter en cada formulario un token
aleatorio que la web mala no conoce. Lo genero con
`secrets.token_urlsafe(16)` al iniciar la sesión, lo pongo disponible
en todas las plantillas con `inject_csrf_token` y en cada POST compruebo
que el formulario trae ese mismo token. Si no coincide, flash de error y
redirección.

### D) Sistema de permisos (`auth.py`)
Además del rol (admin/técnico) hay 31 permisos granulares agrupados por
módulo: Clientes (crear/editar/eliminar/ver), Reparaciones (crear, editar,
eliminar, marcar pagado…), Inventario, Administración… Cuando un usuario
hace login, `obtener_permisos_usuario(rol)` carga en `session["permisos"]`
la lista que le corresponde. Los decoradores `@permiso_requerido(...)` en
las rutas y las comprobaciones `{% if tiene_permiso('...') %}` en las
plantillas hacen que una misma página se vea distinta según quién la
abra. Los admins siempre pasan; los técnicos solo si el permiso está en
su lista. Así puedo tener técnicos que editan reparaciones pero no pueden
borrar clientes.

### E) Transiciones de estado válidas (`historial.py`)
El estado de una reparación no es un campo libre: es una máquina de
estados con transiciones autorizadas. `Pendiente` solo puede ir a `En
proceso`, `En proceso` a `Pendiente` o `Terminado`, `Terminado` a `En
proceso` (arrepentirse) o `Entregado`, y `Entregado` es terminal. Esto lo
aplica `validar_transicion` **solo para técnicos**; los admin pueden saltar
a cualquier estado válido porque a veces hay que corregir errores
operativos. Cada vez que el estado cambia, `registrar_cambio_estado`
mete una fila en `reparaciones_historial` con estado anterior, nuevo,
fecha y usuario responsable. Eso me permite pintar una línea de tiempo
en la ficha de la reparación.

---

## 4. Flujo completo: "qué pasa cuando un cliente paga una reparación con tarjeta"

Este es el recorrido de principio a fin, desde que el cliente pulsa el
botón hasta que recibe el email con la factura en su bandeja.

1. **El cliente entra en la web pública** — Abre `http://androtech/consulta`
   (o escanea el QR del presupuesto, que lleva a `/consulta?id=5`).

2. **Consulta su reparación** — Introduce el número de reparación. La
   función `consulta()` en `app.py` hace un `SELECT` uniendo
   `reparaciones` con `clientes` y le muestra el estado, el precio y,
   si aún no está pagada, un formulario con el botón "Pagar con tarjeta".

3. **Pulsa "Pagar con tarjeta"** — El formulario envía POST a
   `/publico/pagar/<id>` con el email del cliente como verificación.

4. **Validaciones antes de cobrar** — `publico_pagar_reparacion(id)`
   comprueba, en orden: (a) la reparación existe, (b) no está ya pagada,
   (c) tiene precio > 0, (d) el cliente tiene email registrado, (e) el
   email del formulario coincide con el del registro, (f) las claves de
   Stripe están configuradas y son válidas (no una `pk_` puesta por error).

5. **Creación de la sesión de Stripe Checkout** — Si todo cuadra, llamo a
   `stripe.checkout.Session.create(...)` con el importe en céntimos, la
   divisa (EUR), un `product_data` con "Reparación #5 - Nombre", una
   `success_url` (a `/pago_exito?id=5&session_id=...`) y una `cancel_url`
   (de vuelta a `/consulta`). En `metadata` meto `reparacion_id`,
   `cliente_email` y `cliente_nombre` — esto es importantísimo porque
   será lo único que Stripe me devuelva luego para saber qué reparación
   era.

6. **Redirección a Stripe** — `return redirect(checkout_session.url, 303)`.
   El navegador del cliente sale de mi web y va al dominio de Stripe.

7. **El cliente introduce la tarjeta en Stripe** — Mi aplicación **nunca**
   toca los datos de la tarjeta, eso es lo que me protege de PCI-DSS.
   Stripe cobra, emite los recibos internos y gestiona autenticación 3D
   Secure si hace falta.

8. **Stripe redirige al cliente a `success_url`** — Vuelve a mi web a
   `/pago_exito?session_id=cs_test_...&id=5`. La vista `pago_exito` solo
   enseña un "gracias". **Aquí la reparación todavía no está marcada como
   pagada.**

9. **Stripe llama al webhook en paralelo** — Por detrás, Stripe envía un
   POST a `/stripe/webhook` con un JSON que contiene el evento
   `checkout.session.completed` y una cabecera `Stripe-Signature`.

10. **Verificación de firma** — `stripe_webhook()` llama a
    `stripe.Webhook.construct_event(payload, sig_header,
    STRIPE_WEBHOOK_SECRET)`. Si la firma no cuadra (alguien intentando
    falsificar), devuelve 400 y se acabó.

11. **Lectura de metadata** — Del evento saco `reparacion_id` y
    `cliente_email` del `metadata` que yo mismo puse en el paso 5. También
    saco `payment_status` y `amount_total`.

12. **Validaciones de idempotencia y seguridad** — Busco la reparación
    en BD. Si no existe, 404. Si ya estaba `Pagado`, devuelvo 200 sin
    hacer nada (Stripe puede reintentar el webhook, no quiero duplicados).
    Si el importe de Stripe no coincide con mi precio, lo registro como
    warning pero sigo (con tolerancia de 1 céntimo por decimales).

13. **Actualización de la BD** —
    ```
    UPDATE reparaciones
    SET estado_pago='Pagado',
        fecha_pago=hoy,
        metodo_pago='Tarjeta (Stripe)'
    WHERE id=?
    ```
    Y `conn.commit()`.

14. **Registro de auditoría** — `registrar_auditoria(conn,
    'pago_registrado', None, {...})` mete una fila en `audit_log` con
    `session_id` de Stripe y `amount_reported`. Así, si mañana el cliente
    dice "yo pagué", puedo enseñar la entrada.

15. **Generación del PDF de factura** — Cargo otra vez los datos de la
    reparación uniendo con `clientes`, monto el diccionario que espera
    `generar_presupuesto_pdf` y llamo con `tipo_documento="factura"`.
    Devuelve un `BytesIO` con el PDF en memoria (incluye QR con la URL
    correcta porque le paso `request.host_url`).

16. **Envío del email de confirmación** —
    `email_service.send_payment_confirmation(to_email, cliente_nombre,
    reparacion_id, precio, descripcion, pdf_data=pdf_buffer)`. Esta función
    renderiza la plantilla `emails/payment_confirmation.html` y llama al
    `_send` de bajo nivel, que abre conexión SMTP con Gmail
    (`smtp.gmail.com:587`, STARTTLS, login con App Password de 16
    caracteres) y manda el HTML con la factura PDF adjunta. El asunto,
    el remitente y el cuerpo van codificados como UTF-8 (acentos y
    emojis OK) gracias a `email.message.EmailMessage`.

17. **Respuesta al webhook** — `return jsonify({'status': 'received'}),
    200`. Stripe se da por enterado y no reintentará.

18. **El cliente recibe el email** — En su bandeja llega un correo con
    asunto "Confirmacion de Pago - Reparacion #5 - AndroTech", el HTML
    con los datos y la factura PDF adjunta. Al abrirla puede escanear el
    QR con el móvil y volver directamente a `/consulta?id=5` para ver
    que efectivamente pone "Pagado".

19. **(Opcional) En el panel del taller** — La próxima vez que un admin
    abra `/reparaciones`, verá la reparación con la etiqueta verde
    "Pagado". En `/admin/auditoria` aparece la entrada `pago_registrado`.

**Puntos de tranquilidad clave de este flujo:**
- Los datos de tarjeta nunca pasan por mi servidor.
- El estado `Pagado` solo se activa cuando Stripe confirma con firma
  válida — no basta con que el cliente llegue a `success_url`.
- Si el webhook falla (internet caído, Gmail bloqueado, etc.), Stripe
  reintenta varias veces y la idempotencia evita duplicar.
- Toda la cadena queda registrada en `audit_log` con timestamp e IP.

---

*Guía escrita para mí mismo antes de la defensa del TFG — AndroTech v1.0*
*Manuel Cortés Contreras · I.E.S. La Marisma, Huelva · Abril 2026*
