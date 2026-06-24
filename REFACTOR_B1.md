# REFACTOR B1 — monolito `app.py` → blueprints (en curso)

> Rama `saas-migration`. Refactor de **estructura**, no de comportamiento: las
> URLs, los datos y el aislamiento multi-tenant **no cambian**. Gradual, con la
> suite (184 tests + EL JUEZ) **verde tras cada paso** y un commit por blueprint.

## Patrón establecido (`create_app()` + blueprints)

- **`extensions.py`** — `limiter` sin app (se enlaza con `limiter.init_app(app)`
  en la fábrica) + `_resolve_ratelimit_storage`/`_RATELIMIT_STORAGE`.
- **`services.py`** — `email_service` + `notificador` (instancias únicas, sin
  estado de app; `EmailService` lee `current_app.config` al enviar).
- **`app.py`** — `create_app()` devuelve la app-singleton ya configurada
  (`gunicorn app:app` y `app:create_app()` ambos válidos). Re-exporta
  `limiter`/`email_service`/`notificador`/`UPLOAD_FOLDER`/… para que los tests
  (que parchean `app.X`) sigan funcionando sin tocarlos.
- **`blueprints/<dominio>.py`** — cada dominio expone un `Blueprint` SIN
  `url_prefix` (las URLs quedan idénticas). Los endpoints pasan a llamarse
  `dominio.func` (p. ej. `login` → `auth.login`).

### Checklist por blueprint (lo que hay que tocar SIEMPRE al mover uno)

1. Crear `blueprints/<d>.py`, mover las rutas (`@app.route`→`@bp.route`), importar
   dependencias de módulos **no-app** (models, database, utils, extensions,
   services, audit, auth, tokens…). Si una ruta usa un helper que aún vive en
   `app.py`, **primero** extrae ese helper a un módulo compartido (evita ciclos).
2. Dentro de las rutas movidas: `url_for("x")` → `url_for("<d>.x")`.
3. **Fuera** (grep exhaustivo): `url_for` en plantillas y en `app.py`,
   `request.endpoint == 'x'` de la nav (resaltado activo), y las **exenciones por
   endpoint** `_GATE_EXENTAS` / `_CSRF_EXENTAS`.
4. Registrar el blueprint en `app.py` y borrar el código movido.
5. `ruff check` + `pytest` (184 + JUEZ) verde → commit.

## Progreso

| Fase | Estado | Rutas | Endpoints |
|---|---|---|---|
| FASE 0 — andamiaje | ✅ | — | `create_app`, extensions, services |
| auth | ✅ | 6 | `auth.{login,logout,reset_solicitar,reset_confirmar,verificar_email,reenviar_verificacion}` |
| publico | ✅ | 7 | `publico.{index,contacto,sobre,servicios,consulta,mis_reparaciones,solicitar_reparacion}` |
| **clientes** | ✅ | 8 | `clientes.{clientes,nuevo_cliente,editar_cliente,borrar_cliente,historial_cliente,exportar_historial_cliente_pdf,buscar,exportar_clientes_csv}` |
| **inventario** | ✅ | 7 | `inventario.{inventario,nueva_pieza,editar_pieza,eliminar_pieza,api_buscar_piezas,agregar_pieza_reparacion,eliminar_pieza_reparacion}` |
| **cuenta/perfil** | ✅ | 6 | `cuenta.{perfil,cambiar_password,cambiar_email,cambiar_datos_taller,subir_logo_taller,eliminar_logo_taller}` |

**Módulos de helpers compartidos extraídos** (para no ciclar): `csv_utils.py`
(export CSV), `query_helpers.py` (`build_reparaciones_filters`,
`_ultimas_actualizaciones`), **`uploads.py`** (carpetas de subida +
`allowed_file`/`es_imagen_valida`/`_sniff_image_type`), `utils.security.email_valido`.

**`app.py`: 5.301 → 3.906 líneas.** Quedan **~44 rutas** (admin, reparaciones,
facturación/pagos, suscripción, dashboard).

### ✅ `uploads.py` — hecho

Carpetas (`UPLOAD_FOLDER`/`SIGNATURES_FOLDER`/`LOGO_FOLDER`) + validadores
extraídos. Los handlers leen las carpetas por atributo de módulo
(`uploads.LOGO_FOLDER`) en call-time. **conftest fija `UPLOADS_DIR` al tmpdir
ANTES de importar la app**, así `uploads.py` computa las carpetas bajo el tmpdir
al importarse (se eliminaron los parches `app_module.*FOLDER`). Tests de
foto/firma/logo verdes.

## Plan restante (un blueprint por commit, mismo checklist)

> Orden por riesgo/acoplamiento. Cada uno necesita extraer antes sus helpers
> compartidos (indicados) a un módulo común para no ciclar con `app.py`.

1. **admin** — `admin_usuarios, nuevo_usuario, editar_usuario, borrar_usuario,
   admin_roles, nuevo_rol, editar_rol, borrar_rol, admin_auditoria,
   admin_seed_demo, admin_sistema, admin_test_email, admin_solicitudes,
   aceptar_solicitud, rechazar_solicitud, borrar_solicitud`. No usa uploads.
   `admin_seed_demo` es grande (~262 líneas); muévela entera. ~16 rutas.
2. **reparaciones** — `reparaciones, nueva_reparacion, editar_reparacion,
   borrar_reparacion, subir_fotos_reparacion, eliminar_foto_reparacion,
   firmar_reparacion, guardar_firma_reparacion, agregar_nota_reparacion,
   eliminar_nota_reparacion, ticket_recogida, generar_pdf_presupuesto,
   exportar_reparaciones_csv, calendario, api_calendario_eventos`. Helpers:
   `build_reparaciones_filters`, `_ultimas_actualizaciones`, `es_imagen_valida`/
   `allowed_file`/`uploads.*` (✅ ya extraído), PDF. **Bloque caliente** —
   muchos `url_for('editar_reparacion')` en plantillas; ojo: `agregar/
   eliminar_pieza_reparacion` (ya en `inventario`) redirigen a `editar_reparacion`
   → al renombrarlo a `reparaciones.editar_reparacion` hay que actualizar esos
   `url_for` en `blueprints/inventario.py`.
3. **facturacion/pagos** — `marcar_reparacion_pagada, publico_pagar, pago_exito,
   stripe_webhook`. ⚠️ `stripe_webhook` **CSRF-exento** (`_CSRF_EXENTAS`) y por
   **firma de Stripe**: al mover, conservar la exención (ahora
   `pagos.stripe_webhook`) y la verificación de firma intactas.
4. **suscripcion** — `signup, suscripcion, suscripcion_bloqueado,
   suscripcion_portal, saas_webhook`. ⚠️ `saas_webhook` CSRF-exento + firma.
   Mover también la **puerta** `_GATE_EXENTAS`/`puerta_suscripcion` o dejarla en
   la fábrica (es before_request). Actualizar las exenciones a `suscripcion.*`.
   Nota: `signup` usa `email_valido` (✅ en utils.security) + `_slugify`/`_slug_unico`.
5. **dashboard + resto** — `dashboard, healthcheck`. La función `dashboard`
   (~276 líneas, ~20 queries) es la más grande; muévela entera sin trocear su
   lógica.

### Cierre previsto

- Mover los **before_request** (CSP/nonce, `enforce_csrf`, `resolver_taller`,
  `puerta_suscripcion`, sesión permanente), **context processors**
  (`csp_nonce`, `marca`/taller, csrf_token, permisos, email_verificacion) y
  **error handlers** (403/404/429/500) DENTRO de `create_app()` (hoy siguen a
  nivel de módulo en `app.py`). Es seguro hacerlo al final, cuando ya no queden
  rutas a nivel de módulo.
- `app.py` quedará como **entrypoint fino**: config + `create_app()` + registro
  de blueprints. Objetivo orientativo: < 400 líneas.

## Verificación visual para el HUMANO (lo que los tests NO cubren)

Arranca local (`python app.py`) y comprueba el render real:

| URL | Qué verificar |
|---|---|
| `/` (escaparate) | carga; logo/nombre del taller; nav resalta "Inicio"; botón WhatsApp si hay teléfono; **`publico`** |
| `/consulta?codigo=<código real>` | muestra la reparación; nav resalta "Seguimiento"; **`publico`** |
| `/mis-reparaciones` | formulario por email; **`publico`** |
| `/solicitar-reparacion` | enviar el formulario → flash de éxito (redirige a sí mismo); **`publico`** |
| `/login` | entra con admin → va a `/dashboard`; "¿Olvidaste tu contraseña?" lleva a `/reset`; **`auth`** |
| `/reset` | introduce un email → mensaje genérico anti-enumeración; **`auth`** |
| `/logout` (logueado) | cierra sesión y vuelve a `/login`; **`auth`** |
| `/dashboard` | KPIs y gráficos cargan; sidebar resalta "Dashboard" (sigue en `app.py`) |
| `/clientes` | listado paginado (sigue en `app.py`) |
| una ficha `/reparaciones/<id>/editar` | fotos, firma, notas, PDF (sigue en `app.py`) |
| `/perfil` | datos de facturación + logo + acento (sigue en `app.py`) |
| panel admin (`/admin/usuarios`, `/admin/sistema`) | cargan (siguen en `app.py`) |

> Las 3 primeras filas (auth + publico) son las **ya migradas**: si renderizan
> y navegan igual que antes, el patrón es correcto. El resto sigue en `app.py`
> sin cambios (referencia para comparar).
