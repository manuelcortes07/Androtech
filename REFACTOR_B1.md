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
| **admin** | ✅ | 16 | `admin.{admin_usuarios,nuevo_usuario,editar_usuario,borrar_usuario,admin_roles,nuevo_rol,editar_rol,borrar_rol,admin_auditoria,admin_seed_demo,admin_sistema,admin_test_email,admin_solicitudes,aceptar_solicitud,rechazar_solicitud,borrar_solicitud}` |
| **reparaciones** | ✅ | 16 | `reparaciones.{reparaciones,nueva_reparacion,editar_reparacion,borrar_reparacion,subir_fotos_reparacion,eliminar_foto_reparacion,firmar_reparacion,guardar_firma_reparacion,agregar_nota_reparacion,eliminar_nota_reparacion,calendario,api_calendario_eventos,ticket_recogida,generar_pdf_presupuesto,export_reparaciones,exportar_reparaciones_csv}` |
| **pagos** | ✅ | 5 | `pagos.{marcar_reparacion_pagada,publico_pagar,pago_exito,stripe_webhook}` (flujo Stripe de **reparaciones**, api_key global) |
| **suscripcion** | ✅ | 5 | `suscripcion.{signup,suscripcion,suscripcion_bloqueado,suscripcion_portal,saas_webhook}` (flujo Stripe del **SaaS**, StripeClient dedicado) |
| **dashboard** | ✅ | 2 | `dashboard.{dashboard,healthcheck}` |

**Módulos de helpers compartidos extraídos** (para no ciclar): `csv_utils.py`
(export CSV), `query_helpers.py` (`build_reparaciones_filters`,
`_ultimas_actualizaciones`), **`uploads.py`** (carpetas de subida +
`allowed_file`/`es_imagen_valida`/`_sniff_image_type`), `utils.security.email_valido`.

**`app.py`: 5.301 → 671 líneas (−87 %).** **0 `@app.route` restantes**: las
82 reglas de ruta (65 endpoints) viven en **10 blueprints**. `app.py` es ya
config + extensiones + hooks (before_request/context_processor/error_handlers) +
registro de blueprints. Pendiente opcional: envolver esos hooks dentro de
`create_app()` (ver "Cierre" abajo) — hoy corren a nivel de módulo, idénticos.

> **Trampa observada al mover reparaciones**: sus rutas estaban interleadas con
> las **registraciones** de `inventario` y `admin` (insertadas en commits
> anteriores). El slice se las llevó a `reparaciones.py` (donde `app` no existe).
> Solución: quitarlas de `reparaciones.py` y reubicarlas en `app.py`. Lección: al
> hacer slice por rango, comprobar que no engulle líneas `app.register_blueprint`.

> **Técnica para bloques grandes** (admin): mover el bloque por *slice +
> transform* programático (`@app.route`→`@bp.route`, `url_for('X'`→`url_for('admin.X'`,
> `app.config`→`current_app.config`), componer el blueprint con un header de
> imports, y verificar con `ruff --fix` (imports muertos) + suite + un smoke test
> que GET-ea las rutas no cubiertas (sistema/test-email/seed/solicitudes). Funcionó
> en 1 commit verde.

### ✅ `uploads.py` — hecho

Carpetas (`UPLOAD_FOLDER`/`SIGNATURES_FOLDER`/`LOGO_FOLDER`) + validadores
extraídos. Los handlers leen las carpetas por atributo de módulo
(`uploads.LOGO_FOLDER`) en call-time. **conftest fija `UPLOADS_DIR` al tmpdir
ANTES de importar la app**, así `uploads.py` computa las carpetas bajo el tmpdir
al importarse (se eliminaron los parches `app_module.*FOLDER`). Tests de
foto/firma/logo verdes.

## Plan restante — ✅ COMPLETADO (3 blueprints finales)

Los tres dominios más acoplados (los DOS flujos Stripe + la puerta) ya migraron,
verde tras cada movimiento, un commit por blueprint:

1. ✅ **pagos** — `marcar_reparacion_pagada, publico_pagar, pago_exito,
   stripe_webhook`. `stripe_webhook` sigue **CSRF-exento** (`pagos.stripe_webhook`
   en `_CSRF_EXENTAS`), firma **fail-closed** (sin lib → 503), idempotente y con
   control de importe. Reproductores **H4/H8** reapuntados a `blueprints.pagos`
   (parchean ahí `stripe`/`get_session`); **H6** intacto (parchea la lib global).
2. ✅ **suscripcion** — `signup, suscripcion, suscripcion_bloqueado,
   suscripcion_portal, saas_webhook` + helpers (`_slugify/_slug_unico/_sval/
   _taller_por_customer/_saas_aplicar_evento`). `saas_webhook` CSRF-exento
   (`suscripcion.saas_webhook`), firma propia, idempotente, valida `taller_id` de
   la metadata. **La puerta `puerta_suscripcion` se quedó en `app.py`** (es
   before_request: debe correr para TODAS las peticiones); `_GATE_EXENTAS` y su
   `url_for("suscripcion.suscripcion_bloqueado")` actualizados a `suscripcion.*`.
3. ✅ **dashboard** — `dashboard` (KPIs + Chart.js, ~20 queries raw con filtro
   manual `taller_id`) + `healthcheck`. `url_for('dashboard')` reescrito a
   `dashboard.dashboard` en TODO el código + `request.endpoint` de la nav.
   `bool(MAIL_CONFIGURED)` → `_mail_configured()` local (como admin.py).

### Cierre — estado

- ✅ **0 `@app.route` en `app.py`** (grep): las 82 reglas viven en 10 blueprints.
- ✅ **0 referencias `url_for`/`request.endpoint` colgantes** (grep repo-wide).
- ✅ Smoke GET de las rutas movidas (pagos `/pago_exito`, dashboard `/dashboard`
  + `/health`) en `tests/test_branding.py`, como admin/reparaciones.
- ⏭ **PENDIENTE OPCIONAL** (no bloqueante, estructura pura): envolver los
  **before_request** (CSP/nonce, `enforce_csrf`, `resolver_taller`,
  `puerta_suscripcion`, sesión permanente), **context processors** y **error
  handlers** (403/404/429/500) DENTRO de `create_app()`. Hoy corren a nivel de
  módulo sobre la app-singleton — comportamiento idéntico y verificado por la
  suite; moverlos es cosmético. Se deja como paso aparte para no hacer big-bang
  sobre los hooks de seguridad (CSP, CSRF, tenant, gate) en el mismo tramo.
  `app.py` ya es entrypoint sin rutas: **671 líneas** (config + extensiones +
  hooks + registro de 10 blueprints).

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
