# 💻 Guía para instalar AndroTech en el portátil

Esta guía explica, paso a paso, cómo dejar la aplicación AndroTech funcionando
en un segundo ordenador (en este caso el portátil para la exposición) con
exactamente la misma configuración y los mismos datos que en el PC principal.

**Tiempo estimado:** 15–20 minutos.

---

## 📦 1. Requisitos previos (instalar en el portátil)

Instala estos programas **antes** de empezar. Todos son gratuitos.

| Programa | Versión mínima | Dónde descargarlo |
|----------|----------------|-------------------|
| **Python** | 3.11 o superior (3.12 recomendado) | <https://www.python.org/downloads/> |
| **Git** | Cualquier reciente | <https://git-scm.com/download/win> |
| **VS Code** (opcional) | Última | <https://code.visualstudio.com/> |

> ⚠️ Al instalar Python, marca la casilla **"Add Python to PATH"** en la
> primera pantalla del instalador. Sin esto no funcionarán los comandos `python`
> y `pip` desde la terminal.

Comprueba que todo está bien abriendo PowerShell y escribiendo:

```powershell
python --version
git --version
```

Deberías ver las versiones impresas. Si alguno de los dos falla, reinstala con
la opción "Add to PATH" marcada.

---

## 📂 2. Clonar el proyecto desde GitHub

Elige una carpeta donde quieras tener el proyecto (por ejemplo el Escritorio).
Abre PowerShell ahí (Mayús + clic derecho → "Abrir en Terminal") y ejecuta:

```powershell
git clone https://github.com/manuelcortes07/Androtech.git AndroTech
cd AndroTech
```

Esto descarga todo el código fuente. Verás carpetas como `templates/`, `static/`,
`utils/`, `database/`, etc.

---

## 🐍 3. Crear el entorno virtual (venv)

El venv aísla las dependencias del proyecto para no ensuciar la instalación
global de Python.

```powershell
python -m venv venv
```

**Activarlo** (tendrás que hacerlo cada vez que abras una terminal nueva en el
proyecto):

```powershell
.\venv\Scripts\Activate.ps1
```

Si PowerShell te da un error de política de ejecución, ejecuta **una sola vez**:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Cuando el venv esté activo verás `(venv)` al principio de la línea de comandos.

---

## 📚 4. Instalar las dependencias

Con el venv activado:

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

Esto instala Flask, Flask-Mail, Flask-Limiter, Stripe, ReportLab, Pillow, etc.
Tarda 1–2 minutos la primera vez.

---

## 🔐 5. Copiar el fichero `.env` desde el PC principal

El `.env` contiene las claves secretas (Stripe, Gmail, SECRET_KEY) y **NO está
en GitHub** (está en `.gitignore` a propósito — exponer esas claves es un
problema de seguridad grave).

Tienes que copiarlo manualmente del PC principal al portátil:

### Opción A) USB (más rápida)

1. En el PC principal, abre la carpeta del proyecto: `C:\Users\manue\OneDrive\Escritorio\AndroTech`
2. Activa "Mostrar archivos ocultos" en el Explorador (pestaña Vista → casilla "Elementos ocultos").
3. Copia el fichero `.env` al USB.
4. En el portátil, pega el `.env` en la raíz del proyecto clonado (donde está `app.py`).

### Opción B) OneDrive (si ya tienes OneDrive en ambos equipos)

Simplemente copia el `.env` a una carpeta sincronizada por OneDrive y arrástralo
al proyecto del portátil.

### Opción C) Reescribirlo a mano

Si no puedes copiarlo, crea un fichero nuevo llamado `.env` en la raíz del
proyecto con este contenido (sustituye las claves reales):

```env
# Flask
SECRET_KEY=androtech2026huelva_produccion_segura_manuel

# Stripe (test mode)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email (Gmail SMTP con App Password de 16 chars)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USE_SSL=false
MAIL_USERNAME=manuelcortescontreras11@gmail.com
MAIL_PASSWORD=zskz gmfq vqwv pmwk
MAIL_DEFAULT_SENDER=manuelcortescontreras11@gmail.com
```

> ⚠️ Las claves Stripe (`sk_test_...`, `pk_test_...`, `whsec_...`) las tienes
> en el `.env` del PC principal — cópialas tal cual. Son **claves de test**,
> no reales; aun así no las compartas por chat/email.

---

## 🗄️ 6. Inicializar la base de datos

La BD local (`database/andro_tech.db`) tampoco está en git (es un fichero
binario con datos reales). Tienes dos opciones:

### Opción A) Copiar la BD del PC principal (recomendada — mantiene tus datos)

1. En el PC principal, copia la carpeta entera `database/` (contiene `andro_tech.db`).
2. Pégala en el portátil dentro del proyecto (si ya existe, sobrescribe).

### Opción B) Crear una BD vacía nueva

Si no te importa empezar de cero, con el venv activado:

```powershell
python scripts/create_db.py
```

Esto crea las tablas pero no hay usuarios. Para crear el admin:

```powershell
python -c "from app import app, get_db; from werkzeug.security import generate_password_hash; conn = get_db(); conn.execute('INSERT INTO usuarios (usuario, password, rol) VALUES (?, ?, ?)', ('admin', generate_password_hash('admin'), 'admin')); conn.commit(); conn.close(); print('Admin creado: usuario=admin, password=admin')"
```

Cambia la contraseña después del primer login desde `/usuarios`.

---

## ▶️ 7. Arrancar la aplicación

Con el venv activado y dentro de la carpeta del proyecto:

```powershell
python app.py
```

Deberías ver algo como:

```
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://127.0.0.1:5000
```

Abre el navegador en <http://127.0.0.1:5000> y haz login con tu usuario.

---

## ✅ 8. Checklist de verificación

Antes del día de la exposición, comprueba en el portátil:

- [ ] `python app.py` arranca sin errores.
- [ ] Puedes hacer login.
- [ ] Se ven las reparaciones y clientes (si copiaste la BD).
- [ ] Se genera un PDF de presupuesto correctamente (menú Reparaciones → una → PDF).
- [ ] `/admin/sistema` muestra "Email SMTP: Configurado ✓".
- [ ] `/admin/test-email` → "Enviar prueba" → te llega el email (en **local**
      sí debería llegar porque tu red del portátil permite SMTP; el problema
      de Railway es específico de su infraestructura).
- [ ] `/admin/defensa` → abre la presentación de defensa.

---

## 🆘 Problemas frecuentes

### `ModuleNotFoundError: No module named 'flask_limiter'` (o cualquier otro)
Te falta instalar dependencias. Asegúrate de que el venv esté activado y
ejecuta:

```powershell
pip install -r requirements.txt
```

### `python: command not found` / `'python' no se reconoce...`
Python no está en el PATH. Reinstala Python desde <https://python.org/downloads/>
y esta vez **marca "Add Python to PATH"** en la primera pantalla.

### `Activate.ps1 cannot be loaded because running scripts is disabled`
PowerShell no permite ejecutar scripts sin firmar. Ejecuta una sola vez:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### El `.env` no se ve en el Explorador
Windows oculta los archivos que empiezan por punto. Pestaña **Vista** del
Explorador → casilla **"Elementos ocultos"**.

### La BD está vacía tras copiar
Al pegar la carpeta `database/` asegúrate de que pegaste el fichero
`andro_tech.db` dentro, no la carpeta duplicada. La ruta final debe ser
`AndroTech/database/andro_tech.db`.

### Los emails no llegan en local
Vete a `/admin/test-email`. Si sale un error SMTP:
- Verifica que el `.env` tiene `MAIL_USERNAME` y `MAIL_PASSWORD` correctos.
- La App Password de Gmail tiene 16 caracteres (con o sin espacios).
- 2FA en la cuenta de Google debe estar activa.

### El puerto 5000 está ocupado
Si dice `Address already in use`, otra app lo tiene pillado. Arranca en otro
puerto:

```powershell
python app.py --port 5050
```

---

## 🎤 Consejo para la exposición

Para la defensa del TFG, **no dependas de la conexión WiFi del instituto**:

- Arranca la app en `localhost` (no en Railway) → **no necesita internet**.
- Lleva el portátil con la BD cargada de datos demo (la que creaste con
  `/admin/seed-demo`).
- Ten la presentación HTML abierta en una pestaña: `http://localhost:5000/admin/defensa`
- Ten también el PDF de la memoria y las diapositivas en el escritorio, por
  si acaso.

Así, aunque el instituto tenga mal el WiFi, **la demo funciona al 100%**.

---

## 📞 Contacto

**AndroTech — Taller de Reparación de Dispositivos**
Huelva, España
📧 manuelcortescontreras11@gmail.com
📞 +34 633 234 395

---

*Guía preparada para la exposición del TFG — AndroTech v1.0 · Abril 2026*
*Manuel Cortés Contreras · I.E.S. La Marisma, Huelva*
