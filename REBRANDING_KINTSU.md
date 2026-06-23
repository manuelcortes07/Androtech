# REBRANDING → "Kintsu" + branding por taller

> Rama `saas-migration`. El producto (la plataforma SaaS) pasa a llamarse
> **Kintsu** (antes "AndroTech"). Este documento es el registro del trabajo:
> inventario inicial clasificado (Bloque 1), qué cambió por plano (Bloque 2/3),
> campos nuevos en `Taller` + migración, y la verificación final (Bloque 4).

---

## Los dos planos (decisión de diseño)

El rebranding NO es un buscar-y-reemplazar. Hay **dos identidades distintas** que
nunca deben mezclarse:

- **(a) PLATAFORMA = "Kintsu".** Es el SaaS en sí: lo que ven los **dueños/
  técnicos del taller** cuando entran a gestionar. Superficies: el **panel**
  (sidebar/topbar), las páginas de **cuenta** (login, signup, reset, perfil),
  **suscripción**, la **PWA**, los **emails de cuenta** (reset/verificación), el
  README. → todo esto dice **Kintsu**.

- **(b) TALLER = datos del taller (dinámicos, de BD).** Es lo que ven los
  **clientes finales** del taller y lo que firma legalmente el taller.
  Superficies: el **escaparate público** (landing, consulta, mis-reparaciones,
  sobre-nosotros), los **PDF** (presupuesto/factura/ticket/historial), los
  **CSV** de export y los **emails al cliente** (pago, estado, nueva reparación,
  bienvenida). → todo esto sale del **Taller activo** (nombre, dirección,
  teléfono, email, NIF, logo), **nunca** hardcodeado y **nunca** "Kintsu".

> ⚠️ **Matiz de producto importante.** El enunciado del Bloque 2 incluía "textos
> de la landing" dentro de la marca plataforma. Pero la landing actual
> (`index.html`) **no** es una página de marketing de Kintsu: es el **escaparate
> de un taller** ("Reparamos tus dispositivos", WhatsApp a un número concreto,
> "Huelva"). Un cliente de "Reparaciones Pérez" **no** debe ver "Kintsu" ahí.
> Por eso la landing/escaparate se trata como **plano (b) taller-dinámico**, no
> como Kintsu. La marca Kintsu solo aparece, si acaso, como un discreto
> *"Hecho con Kintsu"* al pie. Si en realidad querías una landing de marketing
> de Kintsu separada, dímelo y la separo (sería una página nueva, no esta).

---

## Bloque 1 — Inventario clasificado

Leyenda: **[plataforma]** marca del SaaS → Kintsu · **[taller-hardcode]** dato de
taller incrustado → debe salir de BD · **[seed]** datos del taller demo ·
**[test]** texto fijado en tests · **[doc/comentario]** documentación o
comentarios · **[interno]** identificador técnico no visible como marca
(se justifica dejarlo).

### Plantillas — chrome y títulos

| Fichero / línea | Texto | Clase |
|---|---|---|
| `base.html` :6,50,117,168,170 | `<title>AndroTech ·`, sidebar/topbar/footer `AndroTech`, `© AndroTech` | **[plataforma]** (panel) |
| `base.html` :169 | `Huelva · … · +34 633 234 395` (pie) | **[taller-hardcode]** |
| `base_public.html` :6,47,82,85 | título, nav brand, footer brand, `© AndroTech` | **[taller-hardcode]** (escaparate → nombre del taller) |
| `base_public.html` :84 | `Huelva · … · +34 633 234 395` | **[taller-hardcode]** |
| `login.html` :6,40,87 | título, wordmark, "Sistema de gestión AndroTech" | **[plataforma]** |
| `signup.html` :6,31 | título, wordmark | **[plataforma]** |
| `reset_solicitar.html` :6 · `reset_confirmar.html` :6 | título | **[plataforma]** |
| `suscripcion_bloqueado.html` :6 · `suscripcion.html` :45 | título, "Plan AndroTech" | **[plataforma]** |
| ~25 plantillas del panel | `{% block title %}… - AndroTech{% endblock %}` | **[plataforma]** |
| `index.html` :2,13,19,80 | "en Huelva", "Servicio técnico · Huelva", `wa.me/34633234395` | **[taller-hardcode]** |
| `consulta.html` :133 | "AndroTech nunca almacena tu tarjeta" | **[taller-hardcode]** (es el taller quien cobra) |
| `mis_reparaciones.html` :10,357 | "…tus reparaciones en AndroTech" | **[taller-hardcode]** |
| `sobre_nosotros.html` :10,26,36,… | historia "AndroTech nació en 2018…", "Huelva" | **[taller-hardcode]** (copy de escaparate) |
| `admin_solicitudes.html` :123 | texto WhatsApp "…en AndroTech." | **[taller-hardcode]** |
| `clientes.html` :81 | "Panel administrativo — AndroTech" | **[plataforma]** |
| `admin_test_email.html` :100 | nombre sugerido "AndroTech" para App Password | **[doc/comentario]** (instrucción Gmail) |

### Emails

| Fichero | Texto | Clase |
|---|---|---|
| `emails/bienvenida_cliente.html`, `nueva_reparacion.html`, `payment_confirmation.html`, `repair_status_update.html` | logo/título/footer "AndroTech", "Huelva, España" | **[taller-hardcode]** (taller → su cliente) |
| `emails/reset_password.html`, `verificar_email.html` | (de cuenta) | **[plataforma]** |
| `utils/email_service.py` :126,150,172,194,211,227,240,253 | asuntos "… - AndroTech" | mixto: pago/estado/nueva/bienvenida **[taller-hardcode]**; reset/verify/test **[plataforma]** |

### Documentos generados (PDF / CSV)

| Fichero / línea | Texto | Clase |
|---|---|---|
| `utils/pdf_generator.py` :32-40 (`COMPANY`), 75,248,255,321-322 | nombre/dirección/tel/email/footer "AndroTech / Huelva / +34… / email personal" | **[taller-hardcode]** ← **hallazgo nº1** |
| `app.py` :1957,2036 | PDF historial cliente: título "AndroTech", pie "AndroTech, Huelva \| +34…" | **[taller-hardcode]** |
| `app.py` :3229,3289 | ticket recogida: título "AndroTech", pie "AndroTech, Huelva — +34…" | **[taller-hardcode]** |
| `app.py` :2141-2142,2236 (`_csv_empresa_header`, pie) | "ANDROTECH — Taller…", "Huelva … Tel … email" | **[taller-hardcode]** |
| `app.py` :638,645,2243,2326,4312 | nombres de fichero de descarga "AndroTech_*", "Seed demo - AndroTech" | **[plataforma]**/cosmético (nombre de archivo) |
| `app.py` :1199 | flash "¡Bienvenido a AndroTech! Tu prueba…" | **[plataforma]** |
| `app.py` :2036/2236 etc. "Fin del informe \| AndroTech" | pie de CSV | **[taller-hardcode]** |

### Seed / demo

| Fichero / línea | Texto | Clase |
|---|---|---|
| `migrations.py` :50-56 (`_TALLER_1`) | taller 1: nombre "AndroTech", dir "Huelva, España", email/tel reales | **[seed]** (demo) — pasa a genérico |
| `app.py` :4110-4114 | clientes demo con direcciones "…, Huelva" | **[seed]** |

### Tests

| Fichero | Texto | Clase |
|---|---|---|
| `tests/test_smoke.py`, `test_aislamiento.py`, `conftest.py`, `test_seguridad_auditoria.py` | slug `"androtech"`, `taller_slug`, "Huelva" en datos demo | **[test]**/**[interno]** (slug) |
| `tests/test_pagination.py` :111 | comentario "banner ANDROTECH…" | **[test]** (se actualiza si cambia el banner) |
| `tests/test_pdf.py` :22 | dirección cliente "…, Huelva" | **[test]** (dato de cliente, neutro) |

### Identificadores internos (NO son marca visible — se dejan, justificado)

| Fichero | Identificador | Por qué se deja |
|---|---|---|
| `app.py`, `audit/historial/tenancy/notifications.py` | `logging.getLogger("androtech")`, `logs/androtech.log` | nombre interno de logger/fichero; no es UI |
| `tokens.py` :22-23 | salts `androtech-password-reset` / `-email-verify` | **cambiarlos invalida** todos los tokens vivos (resets/verificaciones en curso) |
| `tenancy.py` :43 | `DEFAULT_TALLER_SLUG = "androtech"` + slug del taller 1 | el slug sale en URLs `/t/androtech/…` y lo fijan tests/QR ya impresos; cambiarlo rompe enlaces y la suite. Es una **clave de tenant**, no la marca del producto |
| `render.yaml`, `.github/workflows/ci.yml`, `.env.example`, `DEPLOY.md` | `androtech-saas`, db `androtech`, `noreply@androtech…` | nombres de servicio/infra; despliegue PAUSADO; se pueden migrar cuando se cree el servicio Kintsu real |
| `static/css/androtech.css` (nombre de fichero), `static/sw.js` `CACHE_NAME='androtech-v1'` | nombre de fichero CSS / cache key | renombrar el fichero obliga a tocar ~40 `url_for(...'androtech.css')`; es ruido sin valor de marca (el usuario no lo ve). El **nombre visible** de la PWA (`manifest.json`) sí pasa a Kintsu |

### TFG — NO se toca

`docs/memoria/**`, `docs/defensa/**`, `INVENTARIO.md`, `INFORME_SAAS.md`,
`AndroTech_Presentacion_Final.html`, etc.: son la **memoria del TFG**. Mantienen
"AndroTech / DoJaMac / Huelva" como corresponde al proyecto académico histórico.

---

## Bloque 2 — Cambios de plataforma → Kintsu

Todo lo que ve el **dueño/técnico** del taller (el SaaS en sí) dice ahora **Kintsu**:

- **Panel** (`base.html`): `<title>`, marca del sidebar y del topbar → "Kintsu".
- **Cuenta/auth**: `login`, `signup`, `reset_solicitar/confirmar`, `suscripcion`,
  `suscripcion_bloqueado` → "Kintsu" (wordmark, títulos, "Plan Kintsu").
- **~22 plantillas del panel**: `{% block title %}… - AndroTech{% endblock %}` →
  `… · Kintsu`.
- **PWA** (`manifest.json`): name/short_name/description → "Kintsu".
- **Emails de cuenta** (`reset_password`, `verificar_email` + asuntos en
  `email_service`) → "Kintsu".
- **Varios** `app.py`: flash de bienvenida del signup, título de la página
  seed-demo, `clientes.html` "Panel administrativo — Kintsu".
- **README**: nota que distingue el TFG (AndroTech) del producto SaaS (Kintsu).

**Puente nuevo** (`branding.py` + context processor `marca`): el escaparate
público y los pies dejan de hardcodear "AndroTech/Huelva/teléfono" y leen el
**taller activo** (o degradan a genéricos). Lo usan tanto el plano (a) como (b).

## Bloque 3 — Branding por taller (arreglo del hallazgo nº1)

El **emisor** de todo documento/comunicación al cliente es ahora el **taller**,
leído de BD, nunca una constante:

| Superficie | Antes | Ahora |
|---|---|---|
| PDF presupuesto/factura (`pdf_generator`) | `COMPANY` = "AndroTech/Huelva" | `taller=` → `_emisor()` (nombre, dir, tel, email, NIF, IVA, logo); default genérico "Taller" |
| PDF historial cliente (`app.py`) | título/pie "AndroTech, Huelva" | `taller_branding()` |
| Ticket de recogida (`app.py`) | título/pie "AndroTech, Huelva" | `taller_branding()` |
| CSV (cabecera/pie/nombre fichero) | "ANDROTECH / Huelva / email" | datos del taller + prefijo de fichero por nombre |
| Emails al cliente (pago/estado/nueva/bienvenida) | logo/footer "AndroTech / Huelva" | `emisor` del taller |
| Escaparate (landing/consulta/mis-reparaciones/sobre) | "AndroTech / Huelva / WhatsApp fijo" | `marca.*`; WhatsApp usa el tel. del taller o se oculta |

**Campo nuevo en `Taller`**: `nif` (TEXT, nullable). Migración idempotente y de
dos motores: columna en el DDL de `talleres` (SQLite) + `asegurar_taller_nif()`
(`ALTER TABLE … ADD COLUMN IF NOT EXISTS`, corre al arrancar). El resto de datos
(nombre, dirección, teléfono, email) ya existían; el IVA, moneda, web y logo
viven en `Taller.config` (JSON). **Logo**: el PDF lo embebe si `config.logo_path`
apunta a un fichero existente; si no, degrada sin logo (aún **no** hay UI de
subida — pendiente menor, documentado).

**UI de ajustes**: `/perfil` gana una tarjeta "Datos de facturación del taller"
(nombre, NIF, dirección, teléfono, IVA %, moneda, web) que postea a la nueva
ruta `POST /perfil/taller` (auto-scoped al taller logueado).

**Degradación**: si un taller no rellenó un dato, el documento simplemente omite
esa línea; el **nombre** sale siempre el del taller (o "Taller"), nunca
"Kintsu"/"AndroTech". El pie lleva un discreto *"Hecho con Kintsu"*.

## Bloque 4 — Seed/demo, tests y verificación

- **Seed/demo**: el taller 1 pasa de "AndroTech / Huelva / contacto real" a
  **"Taller Demo" / "Tu ciudad" / demo@kintsu.app**. Los 5 clientes demo de
  `admin_seed_demo` pierden "Huelva" → "Ciudad Demo". El **slug `androtech`** se
  conserva (clave de tenant en URLs/QR/tests; no es marca visible).
- **Comentarios/docstrings triviales** a Kintsu: `models.py`, `database.py`,
  `email_service.py`, `pdf_generator.py`, `utils/__init__.py`, comentarios de
  diseño en `base*.html`, `check_dependencies.py`, `migrate_sqlite_to_postgres`,
  `admin_test_email` (nombre App Password), `.claude/launch.json`.
- **Tests**: nuevo `tests/test_branding.py` (8): `_emisor`/degradación, **JUEZ de
  aislamiento de marca** (taller A nunca ve los datos de B), `telefono_wa`,
  persistencia de `/perfil/taller`, y **chrome renderizado** (login=Kintsu;
  escaparate=nombre del taller, sin "AndroTech"). Comentario de `test_pagination`
  actualizado.

### Verificación

- **Suite**: **173/173 verde** incl. **EL JUEZ** de aislamiento multi-taller —
  sin cambios en la lógica de negocio ni en el aislamiento.
- **PDF por-taller**: probado que `generar_presupuesto_pdf(..., taller={...})`
  produce un `%PDF` válido con el emisor del taller; con `taller=None` degrada a
  genéricos; `_emisor` nunca devuelve "AndroTech"/"Kintsu". `/perfil/taller`
  persiste los datos y `taller_branding()` los refleja (test + JUEZ).
- **Chrome**: `GET /login` contiene "Kintsu" y **no** "AndroTech"; el escaparate
  (`GET /`) muestra el **nombre del taller** y **no** "AndroTech" (sólo el
  crédito "Hecho con Kintsu").
- **grep final**: 0 apariciones de la marca vieja como identidad de producto u
  operador fuera de: el **TFG** (`docs/**`, informes `.md`), **datos de test**
  neutros, e **identificadores internos justificados** (logger `androtech`, salts
  de tokens, slug `androtech`, nombres de servicio/infra en `render.yaml`/CI/
  `.env.example`, fichero `androtech.css`/`sw.js` cache key). Ver la tabla
  "Identificadores internos" del Bloque 1.

### STOP / pendientes (no incluidos a propósito)

- **Facturación legal (hallazgo nº2)** — serie fiscal continua, NIF obligatorio,
  numeración correlativa por taller — **queda fuera**: es su propio bloque. Hoy
  el "número" sigue siendo `F-{id:05d}` (no una serie fiscal). El campo `nif` ya
  existe pero **no** se valida ni se exige.
- **Subida de logo** (UI): el PDF ya consume `config.logo_path`; falta el
  uploader. Pendiente menor.
- **Infra** (`render.yaml`, CI db, `.env.example`, slug): se migrarán cuando se
  cree el servicio Kintsu real (despliegue PAUSADO).

---

## White-label Nivel 2 — la marca del taller donde la ve el CLIENTE

Extensión posterior: el **logo** del taller (subible) en el portal del cliente,
los emails y los documentos; más un **color de acento** por taller.

### Superficies del cliente que ya muestran la marca del taller

| Superficie | Qué muestra |
|---|---|
| Escaparate (landing/`sobre`) | logo (o hexágono) + nombre en cabecera y footer |
| Portal de seguimiento (`/consulta`, `mis-reparaciones`) | **logo del taller dueño de la reparación** (resuelto por el código), nunca el de otro |
| Emails al cliente (pago/estado/nueva/bienvenida) | logo en la cabecera (URL absoluta) o el nombre |
| PDF/ticket/CSV (Nivel 1) | logo embebido si existe + datos del taller |
| Panel / login / emails de cuenta | **Kintsu** (no cambia: es la plataforma) |

### Cómo se resuelve el logo

- Se sube en `/perfil` (`POST /perfil/logo`, quitar en `/perfil/logo/eliminar`)
  reutilizando la validación segura existente (magic bytes, allowlist **sin
  SVG**, 5 MB, nombre aleatorio). Se guarda en `UPLOADS_DIR/logos/` y en
  `Taller.config.logo_file` (sólo el nombre de fichero).
- `branding.taller_branding()` deriva tres formas del mismo logo:
  `logo_path` (ruta de **fichero**, para embeber en el PDF), `logo_static`
  (ruta relativa para `url_for('static', …)` en **web**) y, vía
  `logo_url_absoluto()`, una **URL absoluta** para los **emails**.
- **Emails en segundo plano**: los uploads se sirven como **estático público**
  (`/static/uploads/logos/…`), así que **no hace falta infra extra de hosting de
  imágenes**. La URL absoluta usa el host de la petición o `APP_BASE_URL`; si no
  hay forma de construirla, degrada al nombre (el envío nunca se rompe).
  ⚠️ En **dev puro local** el cliente de correo del destinatario no alcanza
  `localhost` → el logo no carga (sólo visual; el nombre sí aparece). En
  producción con host público funciona.

### Color de acento por taller (Bloque 4 — ACTIVADO)

- Campo opcional `Taller.config.accent_color` (hex `#RRGGBB`, validado en
  servidor; basura se descarta). Se edita en `/perfil`.
- Si está, se **inyecta** un `<style nonce="…">` (CSP-safe) que sobrescribe
  `--accent`/`--accent-2`/`--accent-soft` **sólo en las superficies del cliente**
  (`base_public.html` y la rama sin-login de `base.html`). El **panel Kintsu
  nunca** lo usa (gate `{% if not session.usuario %}`). Si está vacío, azul por
  defecto. Lo decidí **activar** porque es de bajo riesgo (valor validado +
  nonce vigente) y de alto impacto white-label.

### Aislamiento (JUEZ ampliado)

`tests/test_branding.py` (19): subida válida/trucada, quitar, **JUEZ logo no
cruza de taller** (subir en taller 1 no toca al 2), **JUEZ portal** (consultar un
código del taller 2 pinta el logo del 2, nunca el del 1), logo en email (URL
absoluta vs degradación), acento válido inyectado / inválido descartado / panel
sin acento del taller. **184/184 verde** incl. EL JUEZ de aislamiento.

### Pendiente

- Validación **opcional** de dimensiones/relación de aspecto del logo (hoy se
  acepta cualquier imagen válida ≤ 5 MB; el CSS la encuadra con `object-fit`).
