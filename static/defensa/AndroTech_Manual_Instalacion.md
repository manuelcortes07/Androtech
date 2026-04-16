# Manual de Instalación y Despliegue — AndroTech

**Sistema de Gestión para Taller Técnico de Reparaciones**

**Autor:** Manuel Cortés Contreras  
**Versión:** 1.0  
**Fecha:** Abril 2026  
**Centro:** I.E.S. La Marisma, Huelva

---

## Introducción

Este manual explica cómo instalar y poner en marcha AndroTech, tanto en un entorno local para desarrollo y pruebas como en un servidor de producción accesible desde Internet.

He intentado que los pasos sean lo más claros posible, pero es necesario tener conocimientos básicos de terminal y de Python para seguirlos sin problemas.

---

## Requisitos previos

Antes de empezar, hay que tener instalado lo siguiente en el sistema:

| Software | Versión mínima | Dónde descargarlo |
|----------|---------------|-------------------|
| Python | 3.10 o superior | https://www.python.org/downloads |
| Git | Cualquier versión reciente | https://git-scm.com |
| Navegador web moderno | Chrome, Firefox o Edge actualizado | — |

Para comprobar que Python está instalado correctamente, abre una terminal y ejecuta:

```bash
python --version
```

Debería aparecer algo como `Python 3.12.x`. Si aparece un error, revisa la instalación de Python.

---

## Instalación en entorno local (Windows)

### Paso 1 — Clonar el repositorio

Abre una terminal (PowerShell o CMD) en la carpeta donde quieras instalar el proyecto y ejecuta:

```bash
git clone https://github.com/manuelcortes07/Androtech.git
cd Androtech
```

Si no tienes Git instalado también puedes descargar el proyecto directamente desde GitHub como archivo ZIP y descomprimirlo.

---

### Paso 2 — Crear el entorno virtual

Es muy recomendable usar un entorno virtual para que las dependencias del proyecto no interfieran con otras instalaciones de Python del sistema.

```bash
python -m venv venv
```

Activar el entorno virtual en Windows:

```bash
venv\Scripts\activate
```

Sabrás que está activo porque el nombre del entorno aparece entre paréntesis al principio de la línea de comandos: `(venv)`.

---

### Paso 3 — Instalar las dependencias

Con el entorno virtual activado, instala todas las librerías necesarias:

```bash
pip install -r requirements.txt
```

Este proceso puede tardar unos minutos dependiendo de la velocidad de la conexión. Al terminar, todas las dependencias estarán instaladas.

---

### Paso 4 — Configurar las variables de entorno

El proyecto usa un fichero `.env` para almacenar todas las configuraciones sensibles (claves de Stripe, credenciales de email, etc.) de forma que nunca se suban al repositorio de GitHub.

Copia el fichero de ejemplo:

```bash
copy .env.example .env
```

Abre el fichero `.env` con un editor de texto y rellena los valores:

```env
# Clave secreta de Flask (pon cualquier cadena larga y aleatoria)
SECRET_KEY=pon_aqui_una_clave_secreta_larga

# Claves de Stripe (se obtienen en dashboard.stripe.com)
STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Configuración del email (ejemplo con Gmail)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=tu_email@gmail.com
MAIL_PASSWORD=tu_contraseña_de_aplicacion
```

> Si solo quieres probar la aplicación en local sin pagos ni emails, puedes dejar las claves de Stripe y email en blanco. La aplicación funcionará igualmente, pero esas funcionalidades no estarán disponibles.

---

### Paso 5 — Inicializar la base de datos

Ejecuta el script de creación de la base de datos:

```bash
python create_db.py
```

Esto crea el fichero `database/andro_tech.db` con todas las tablas y los datos iniciales, incluyendo los usuarios de prueba.

---

### Paso 6 — Arrancar la aplicación

```bash
python app.py
```

Si todo ha ido bien, verás algo como:

```
 * Running on http://127.0.0.1:5000
 * Debug mode: on
```

Abre el navegador y ve a `http://127.0.0.1:5000`. Deberías ver la página de inicio de AndroTech.

---

### Credenciales de prueba

| Usuario | Contraseña | Rol |
|---------|-----------|-----|
| admin | admin123 | Administrador |
| tecnico | tecnico123 | Técnico |

> Cambia estas contraseñas antes de usar la aplicación con datos reales.

---

## Configuración de Stripe (pagos online)

Para que los pagos funcionen hay que crear una cuenta gratuita en Stripe y obtener las claves de API.

### Obtener las claves de Stripe

1. Crear una cuenta en https://dashboard.stripe.com
2. En el panel, ir a **Developers → API Keys**
3. Copiar la **Publishable key** (empieza por `pk_test_`) y la **Secret key** (empieza por `sk_test_`)
4. Pegar estas claves en el fichero `.env`

### Configurar el webhook de Stripe

El webhook es la forma que tiene Stripe de notificar a la aplicación cuando se completa un pago. Para configurarlo en local se usa la herramienta Stripe CLI.

1. Instalar Stripe CLI desde https://stripe.com/docs/stripe-cli
2. Autenticarse:
```bash
stripe login
```
3. Iniciar el reenvío de webhooks al servidor local:
```bash
stripe listen --forward-to localhost:5000/stripe/webhook
```
4. Copiar el webhook secret que aparece en la terminal (empieza por `whsec_`) y pegarlo en `.env`

---

## Configuración del email (Gmail)

Para que los emails automáticos funcionen con Gmail hay que generar una contraseña de aplicación (distinta de la contraseña normal de la cuenta).

1. Entrar en la cuenta de Google
2. Ir a **Gestionar tu cuenta Google → Seguridad**
3. Activar la **Verificación en dos pasos** si no está activa
4. Buscar **Contraseñas de aplicaciones** y generar una nueva para "Correo" en "Otro dispositivo"
5. Copiar la contraseña generada (16 caracteres) y pegarla en `MAIL_PASSWORD` en el fichero `.env`

---

## Instalación en producción (Railway.app)

Railway es una plataforma de hosting gratuita que permite desplegar aplicaciones Python con muy pocos pasos. Es la opción más sencilla para tener AndroTech accesible desde Internet.

### Paso 1 — Crear cuenta en Railway

Ir a https://railway.app y crear una cuenta gratuita (se puede usar la cuenta de GitHub directamente).

### Paso 2 — Crear un proyecto nuevo

1. En el panel de Railway, hacer clic en **New Project**
2. Seleccionar **Deploy from GitHub repo**
3. Conectar la cuenta de GitHub y seleccionar el repositorio `Androtech`

### Paso 3 — Configurar las variables de entorno

En el panel del proyecto en Railway, ir a **Variables** y añadir todas las variables del fichero `.env`:

- `SECRET_KEY`
- `STRIPE_PUBLIC_KEY`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `MAIL_SERVER`
- `MAIL_PORT`
- `MAIL_USERNAME`
- `MAIL_PASSWORD`

### Paso 4 — Configurar el comando de inicio

Railway necesita saber cómo arrancar la aplicación. En la configuración del proyecto, en **Settings → Deploy**, establecer el comando de inicio:

```bash
gunicorn app:app
```

Para que Gunicorn esté disponible hay que añadirlo a `requirements.txt`:

```
gunicorn==21.2.0
```

### Paso 5 — Desplegar

Railway desplegará automáticamente la aplicación cuando se hace push al repositorio de GitHub. El panel muestra los logs del despliegue en tiempo real. Cuando aparece el mensaje de que el despliegue fue exitoso, Railway asigna una URL pública con formato `https://nombreproyecto.railway.app`.

### Paso 6 — Inicializar la base de datos en producción

Una vez desplegado, hay que ejecutar el script de creación de la base de datos. Desde el panel de Railway, ir a **Deploy → Console** y ejecutar:

```bash
python create_db.py
```

### Paso 7 — Actualizar el webhook de Stripe

En el panel de Stripe, ir a **Developers → Webhooks → Add endpoint** e introducir la URL del webhook del servidor de producción:

```
https://tuproyecto.railway.app/stripe/webhook
```

Seleccionar el evento `checkout.session.completed` y guardar. Copiar el webhook secret generado y actualizarlo en las variables de entorno de Railway.

---

## Actualizar la aplicación

Cada vez que se hace un commit y push al repositorio de GitHub, Railway detecta el cambio y redesplega automáticamente la aplicación. No es necesario hacer nada más.

Para actualizar en local, simplemente hacer pull del repositorio y reiniciar el servidor:

```bash
git pull origin main
python app.py
```

---

## Solución de problemas frecuentes

**Error: `ModuleNotFoundError`**
Significa que alguna dependencia no está instalada. Asegúrate de que el entorno virtual está activado y ejecuta `pip install -r requirements.txt` de nuevo.

**Error: `No such file or directory: database/andro_tech.db`**
La base de datos no se ha creado todavía. Ejecuta `python create_db.py`.

**La aplicación arranca pero los pagos no funcionan**
Comprueba que las claves de Stripe en el fichero `.env` son correctas y que el servidor de webhook está escuchando. Revisa los logs de la consola para ver si hay mensajes de error relacionados con Stripe.

**Los emails no se envían**
Comprueba que las variables `MAIL_*` en el fichero `.env` son correctas. Si usas Gmail, asegúrate de que estás usando una contraseña de aplicación y no la contraseña normal de la cuenta.

**Error 429 en el login**
Se ha superado el límite de intentos de login (5 por minuto). Espera un minuto e inténtalo de nuevo.

---

## Estructura de ficheros generados en runtime

Estos ficheros se generan automáticamente cuando la aplicación se ejecuta por primera vez y no deben subirse al repositorio:

| Fichero | Descripción |
|---------|-------------|
| `database/andro_tech.db` | Base de datos SQLite |
| `static/uploads/` | Fotos subidas de reparaciones |
| `logs/androtech.log` | Log de la aplicación |
| `.env` | Variables de entorno (nunca subir a GitHub) |

---

*Manual de instalación — AndroTech v1.0 · Abril 2026*  
*Desarrollado por Manuel Cortés Contreras · I.E.S. La Marisma, Huelva*
