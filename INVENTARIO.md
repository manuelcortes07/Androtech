# 📦 Inventario del repositorio AndroTech

> Informe **solo lectura**. Pensado para decidir qué reorganizar antes de
> presentar el repo a un evaluador externo. No se ha movido ni borrado nada.
>
> Generado el 2026-05-04.
> Excluidos del análisis: `venv/`, `__pycache__/`, `.git/`, `node_modules/`,
> `.venv/`.

---

## 1. Listado completo de la raíz

### Ficheros (29)

| Fichero | Tamaño | Tipo |
|---------|--------|------|
| `.env` | 669 B | Variables secretas (Stripe, Gmail, SECRET_KEY) |
| `.env.example` | 1.7 KB | Plantilla de `.env` para nuevos clones |
| `.gitignore` | 51 B | Excluye `venv/`, `__pycache__/`, `*.db`, `logs/`, `.env` |
| `Procfile` | 84 B | Comando de arranque para Railway/Heroku |
| `requirements.txt` | 414 B | Dependencias Python |
| `runtime.txt` | 14 B | Pin de versión Python (3.12.0) |
| `app.py` | 162 KB | **Aplicación Flask completa** |
| `db.py` | 379 B | Conexión SQLite |
| `auth.py` | 8.2 KB | Sistema de permisos y decoradores |
| `audit.py` | 4.1 KB | Registro de auditoría |
| `alerts.py` | 2.7 KB | Cálculo de alertas del dashboard |
| `historial.py` | 2.7 KB | Transiciones de estado |
| `check_admin.py` | 1.4 KB | Script de debug del usuario admin |
| `check_dependencies.py` | 2.0 KB | Script para verificar pip install |
| `check_pw.py` | 265 B | Script de debug de contraseña admin |
| `create_db.py` | 1.4 KB | Inicializador de la BD desde cero |
| `androtech.db` | 0 B | **Fichero vacío** (la BD real está en `database/`) |
| `index.html` | 13.4 KB | Página HTML estática suelta en raíz |
| `AndroTech_Documento_Proyecto.docx` | 637 KB | Memoria del TFG (Word) |
| `AndroTech_Documento_Proyecto_Cap1.md` | 12 KB | Memoria capítulo 1 |
| `AndroTech_Documento_Proyecto_Cap2.md` | 21 KB | Memoria capítulo 2 |
| `AndroTech_Documento_Proyecto_Cap3_Cap4.md` | 21 KB | Memoria capítulos 3-4 |
| `AndroTech_Documento_Proyecto_Cap5_Cap6_Cap7_Final.md` | 29 KB | Memoria capítulos 5-7 |
| `AndroTech_Manual_Instalacion.md` | 9.6 KB | Manual de instalación TFG |
| `AndroTech_Manual_Usuario.md` | 12 KB | Manual de usuario TFG |
| `AndroTech_Parte1_Caps1-4.odt` | 61 KB | Versión ODT (LibreOffice) de la memoria |
| `AndroTech_Preguntas_Tribunal.md` | 12 KB | Posibles preguntas del tribunal |
| `AndroTech_Presentacion_Final.html` | 1.06 MB | Presentación HTML standalone |
| `EMAIL_SETUP.md` | 3.6 KB | Guía SMTP antigua |
| `GMAIL_SETUP.md` | 3.5 KB | Guía Gmail App Password |
| `GUIA_CODIGO.md` | 18 KB | Guía interna del código (recién creada) |
| `INSTALAR_EN_PORTATIL.md` | 8.4 KB | Tutorial portátil de la defensa |
| `PAYMENT_UI_IMPROVEMENTS.md` | 7.2 KB | Notas de UI de pago |
| `README.md` | 8.9 KB | README principal |
| `TESTING_PAYMENTS.md` | 4.0 KB | Guía de testing Stripe |
| `WEBHOOK_SETUP.md` | 5.4 KB | Configuración webhook Stripe |

### Carpetas (8)

`.claude/`, `.vscode/`, `database/`, `logs/`, `static/`, `templates/`, `utils/`, `__pycache__/`

---

## 2. Ficheros `.py` de la raíz — qué hacen y quién los importa

| Fichero | Qué hace en una línea | ¿Importado? | Estado |
|---------|----------------------|-------------|--------|
| `app.py` | Aplicación Flask completa: rutas, config, arranque. | Es el `entrypoint`. Lo arranca Gunicorn (Procfile) y `python app.py`. | ✅ ACTIVO |
| `db.py` | `get_db()` devuelve conexión SQLite con `row_factory`. | `app.py`, `auth.py`, `historial.py`, `audit.py`, `alerts.py`, `check_admin.py`, `check_pw.py`. | ✅ ACTIVO |
| `auth.py` | 31 permisos, decoradores `@login_required`, `@permiso_requerido`. | `app.py`. | ✅ ACTIVO |
| `audit.py` | `registrar_auditoria()` y consulta de `audit_log`. | `app.py`. | ✅ ACTIVO |
| `alerts.py` | `calcular_alertas_reparacion()` para el dashboard. | `app.py`. | ✅ ACTIVO |
| `historial.py` | Validación de transiciones de estado y registro en `reparaciones_historial`. | `app.py`. | ✅ ACTIVO |
| `create_db.py` | Crea las tablas básicas de la BD desde cero (script one-shot). | Nadie lo importa, pero **referenciado en `INSTALAR_EN_PORTATIL.md`** como paso de setup. | 🟡 ACTIVO (script, no módulo) |
| `check_admin.py` | Script de debug: lista usuarios y resetea password admin a `admin123` si falla. | **Nadie lo importa.** | 🔴 HUÉRFANO — script de debug suelto. |
| `check_dependencies.py` | Script que comprueba si están instaladas las dependencias clave. | **Nadie lo importa.** | 🔴 HUÉRFANO — utilidad de desarrollo. |
| `check_pw.py` | 8 líneas, imprime hash de contraseña del admin. | **Nadie lo importa.** | 🔴 HUÉRFANO — script de debug suelto. |

**Resumen:**
- 6 módulos importados activamente por `app.py`.
- 1 script de inicialización legítimo (`create_db.py`) referenciado en docs.
- 3 scripts de debug huérfanos (`check_admin.py`, `check_dependencies.py`, `check_pw.py`) que no aporta nada al código de producción y un evaluador no debería verlos en la raíz.

---

## 3. Ficheros `.md` de la raíz — contenido y obsolescencia

| Fichero | Qué contiene | Estado |
|---------|--------------|--------|
| `README.md` | Descripción, características, instalación, despliegue, capturas. Es el escaparate del proyecto. | 🟡 **Parcialmente obsoleto.** Menciona el taller real *"DoJaMac Informática – Andropple"* en línea 12 — esto se cambió en otros documentos a `AndroTech` con tu contacto real, pero aquí sigue. Revisar antes de entregar. |
| `GUIA_CODIGO.md` | Guía interna del código (lista de ficheros, 10 funciones clave, partes complejas, flujo de pago). Generado hoy. | ✅ AL DÍA |
| `INSTALAR_EN_PORTATIL.md` | Tutorial paso a paso para instalar en el portátil de la defensa. | ✅ AL DÍA (creado hace pocos días) |
| `EMAIL_SETUP.md` | Guía SMTP genérica. Habla de Flask-Mail y referencia un script `configure_email.ps1` que **no existe en el repo**. | 🔴 **OBSOLETO.** Flask-Mail fue sustituido por `smtplib`+`EmailMessage` en `utils/email_service.py`. La info contradice al código actual. |
| `GMAIL_SETUP.md` | Cómo crear un App Password de Gmail (2FA + 16 chars). | 🟡 Sigue siendo válida, pero el contenido se duplica con `INSTALAR_EN_PORTATIL.md` y con `EMAIL_SETUP.md`. |
| `WEBHOOK_SETUP.md` | Configurar webhook de Stripe en local (stripe-cli) y producción. | ✅ AL DÍA — los pasos coinciden con `stripe_webhook()` en `app.py`. |
| `TESTING_PAYMENTS.md` | Guía de pruebas end-to-end del flujo de pago en local. | ✅ AL DÍA — sigue siendo válida. |
| `PAYMENT_UI_IMPROVEMENTS.md` | Bitácora de cambios estéticos del flujo de pago. | 🟡 **Documento histórico.** Útil como changelog, no como guía. Probablemente debería ir a un `docs/historico/` o eliminarse. |
| `AndroTech_Documento_Proyecto_Cap1.md` | Memoria TFG cap. 1 (introducción y objetivos). | 🟡 Es la memoria oficial — **pero los 4 capítulos `.md` están duplicados en `static/defensa/`**, que es donde realmente los sirve `/admin/defensa`. Mantener una sola copia. |
| `AndroTech_Documento_Proyecto_Cap2.md` | Memoria TFG cap. 2 (análisis y diseño). | 🟡 Idem — duplicado en `static/defensa/`. |
| `AndroTech_Documento_Proyecto_Cap3_Cap4.md` | Memoria TFG caps. 3-4 (implementación). | 🟡 Idem — duplicado en `static/defensa/`. |
| `AndroTech_Documento_Proyecto_Cap5_Cap6_Cap7_Final.md` | Memoria TFG caps. 5-7 (pruebas, despliegue, conclusiones). | 🟡 Idem — duplicado en `static/defensa/`. |
| `AndroTech_Manual_Instalacion.md` | Manual de instalación oficial del TFG. | 🟡 Duplicado en `static/defensa/AndroTech_Manual_Instalacion.md`. |
| `AndroTech_Manual_Usuario.md` | Manual de usuario oficial del TFG. | 🟡 Duplicado en `static/defensa/AndroTech_Manual_Usuario.md`. |
| `AndroTech_Preguntas_Tribunal.md` | Posibles preguntas del tribunal. | ✅ Actual. Solo existe en raíz, no duplicado. |

**Patrón detectado:** los documentos del TFG (memoria + manuales) están **duplicados literalmente** en `static/defensa/`. La copia de `static/defensa/` es la que sirve la ruta `/admin/defensa`, así que la copia de la raíz es redundante.

---

## 4. Carpetas en la raíz

### `.claude/` — ✅ activa
Configuración del entorno de desarrollo Claude Code:
- `launch.json` — config de debug VS Code.
- `settings.local.json` — permisos locales del agente.
- `worktrees/` — worktrees git (incluyendo este, `cool-panini`).

> Es metadata del entorno, no código de la app. **Ignorable para evaluador.**

### `.vscode/` — ✅ activa
- `settings.json` — configuración de VS Code (260 B).

### `__pycache__/` — 🔴 basura
Bytecode compilado de Python. **Ya está en `.gitignore`**, pero la carpeta sigue existiendo localmente. Inofensiva pero no aporta nada.

### `database/` — ✅ activa
- `andro_tech.db` (100 KB) — **la base de datos SQLite real** de la aplicación.

> Cuidado: hay otro fichero `androtech.db` (0 B, sin guion bajo) en la **raíz**. Es un duplicado vacío que se creó por error. Ver sección 5.

### `logs/` — 🟡 activa pero no commiteable
- `androtech.log` (18 KB) — Log de la aplicación.

> En `.gitignore`. La carpeta existe localmente porque la app escribe ahí.

### `static/` — ✅ activa
Recursos estáticos servidos por Flask:
- `style.css` (raíz de `css/`) — estilos principales.
- `style.css.backup` — **backup viejo de 24 KB. Basura.** Ver sección 5.
- `favicon.svg`, `manifest.json`, `sw.js` — PWA.
- `favicons/` — 7 PNG + ico (varios tamaños).
- `imagenes/logo.jpg` — logo corporativo.
- `defensa/` — copias servidas de la memoria + manuales + presentación HTML (1.06 MB) + `README.md` duplicado. Servida por `/admin/defensa`.
- `doc_screenshots/` — 8 capturas PNG + un `screenshots_b64.json` (1 MB) que no se ve referenciado en código y parece haber sido un artefacto temporal de algún script de generación.
- `uploads/firmas/`, `uploads/reparaciones/` — destino de subidas de cliente. Vacíos en el repo, se llenan en runtime.

### `templates/` — ✅ activa
40+ plantillas Jinja organizadas por entidad (clientes, reparaciones, admin, emails). Una observación:
- `templates/factura.html` — **0 bytes** (fichero vacío). Sin uso.
- `templates/index.html` — versión Flask de la portada.

### `utils/` — ✅ activa
- `__init__.py` (31 B)
- `email_service.py` (10.5 KB) — envío SMTP nativo.
- `pdf_generator.py` (13.7 KB) — generación de PDF con QR.
- `security.py` (2.2 KB) — CSRF y validadores.
- `__pycache__/` — bytecode (ignorable).

---

## 5. Ficheros temporales, basura o duplicados

Esto es lo que un evaluador externo notaría como "ruido" o lo que conviene
limpiar antes de entregar. **No estoy borrando nada, solo señalando.**

### 🔴 Probable basura / temporal

| Fichero | Por qué es sospechoso |
|---------|----------------------|
| `androtech.db` (raíz) | **0 bytes**. La BD real es `database/andro_tech.db` (con guion bajo). Este fichero se creó por error o por un script con la ruta mal escrita. |
| `static/css/style.css.backup` | Backup manual de 24 KB del CSS antiguo. Ya tienes Git, no necesitas backups en el árbol. |
| `templates/factura.html` | **0 bytes**. Plantilla vacía sin uso ni referencia desde `app.py`. |
| `__pycache__/` (raíz) | Bytecode compilado. Ignorado por Git pero presente en local. |
| `static/doc_screenshots/screenshots_b64.json` | 1 MB de imágenes en base64 dentro de un JSON. No se referencia desde el código activo; parece intermedio de un script de generación. Las PNG sueltas sí se usan. |

### 🔴 Scripts de debug huérfanos

| Fichero | Comentario |
|---------|------------|
| `check_admin.py` | Script de debug. Resetea la password del admin a `admin123` si no coincide. **Peligroso dejarlo en producción** — un atacante con acceso al filesystem podría ejecutarlo. |
| `check_pw.py` | 8 líneas que imprimen el hash de la contraseña del admin. Solo sirvió para depurar una vez. |
| `check_dependencies.py` | Comprueba `pip install`. Útil en su día, pero hoy `pip install -r requirements.txt` y el README hacen el mismo trabajo. |

### 🟡 Documentación duplicada

| Original (raíz) | Copia |
|-----------------|-------|
| `AndroTech_Documento_Proyecto_Cap1.md` | `static/defensa/AndroTech_Documento_Proyecto_Cap1.md` |
| `AndroTech_Documento_Proyecto_Cap2.md` | `static/defensa/AndroTech_Documento_Proyecto_Cap2.md` |
| `AndroTech_Documento_Proyecto_Cap3_Cap4.md` | `static/defensa/AndroTech_Documento_Proyecto_Cap3_Cap4.md` |
| `AndroTech_Documento_Proyecto_Cap5_Cap6_Cap7_Final.md` | `static/defensa/AndroTech_Documento_Proyecto_Cap5_Cap6_Cap7_Final.md` |
| `AndroTech_Documento_Proyecto.docx` | `static/defensa/AndroTech_Documento_Proyecto.docx` |
| `AndroTech_Manual_Instalacion.md` | `static/defensa/AndroTech_Manual_Instalacion.md` |
| `AndroTech_Manual_Usuario.md` | `static/defensa/AndroTech_Manual_Usuario.md` |
| `AndroTech_Presentacion_Final.html` | `static/defensa/AndroTech_Presentacion_Final.html` |
| `README.md` | `static/defensa/README.md` |

> La copia "buena" para la app es la de `static/defensa/` (es la que sirve
> `/admin/defensa`). La de la raíz puede confundir al evaluador y aumenta
> el riesgo de que las dos versiones se desincronicen al editar.

### 🟡 Documentación obsoleta o redundante

| Fichero | Problema |
|---------|----------|
| `EMAIL_SETUP.md` | Habla de Flask-Mail y de un script `configure_email.ps1` inexistente. El sistema actual usa `smtplib` directamente. |
| `GMAIL_SETUP.md` | Contenido muy solapado con `EMAIL_SETUP.md` y con la sección de Gmail de `INSTALAR_EN_PORTATIL.md`. |
| `PAYMENT_UI_IMPROVEMENTS.md` | Bitácora histórica, no documentación viva. |
| `index.html` (raíz) | HTML estático suelto que no es servido por Flask (Flask usa `templates/index.html`). Parece una landing antigua o un experimento que se quedó. |
| `AndroTech_Parte1_Caps1-4.odt` | Versión ODT antigua de la memoria. Ya tienes la versión `.docx` actualizada y los `.md` por capítulo. Probable basura histórica. |

---

## 📝 Recomendaciones (resumen para reorganizar)

Cuando decidas mover/eliminar (en otra sesión, no aquí):

1. **Crear `scripts/`** y mover ahí `check_admin.py`, `check_pw.py`, `check_dependencies.py`, `create_db.py`. Mantiene la raíz limpia.
2. **Crear `docs/`** y mover ahí toda la documentación de la memoria del TFG, manuales y guías técnicas. Dejar en raíz solo `README.md`, `INSTALAR_EN_PORTATIL.md` y `GUIA_CODIGO.md`.
3. **Eliminar duplicados**: decidir si la documentación oficial vive en `docs/` (la app la copia a `static/defensa/` en build) o solo en `static/defensa/`.
4. **Borrar basura**: `androtech.db` (0 B en raíz), `style.css.backup`, `templates/factura.html` (0 B), `__pycache__/`, posiblemente `screenshots_b64.json`.
5. **Actualizar `EMAIL_SETUP.md`** para reflejar que ya no se usa Flask-Mail, o fusionarlo con `GMAIL_SETUP.md` y `INSTALAR_EN_PORTATIL.md` en un único `docs/EMAIL.md`.
6. **Decidir `index.html` raíz**: o se elimina, o se documenta para qué sirve.
7. **Revisar `README.md`**: la línea 12 sigue mencionando "DoJaMac Informática – Andropple"; en otros documentos ya se cambió a `AndroTech` con tu contacto real.

---

*Inventario generado para la reorganización del repositorio AndroTech.*
*Solo lectura — ningún fichero ha sido movido, borrado o modificado.*
