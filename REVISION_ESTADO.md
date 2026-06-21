# REVISIÓN DE ESTADO — AndroTech (rama `saas-migration`)

> Modo diagnóstico (NO se tocó código). Fecha: 2026-06-21. Revisor: arquitecto/tech-lead.
> Honesto y accionable. Donde no pude verificar algo, lo marco como **[a verificar]**.

---

## Resumen ejecutivo

AndroTech es un proyecto **sorprendentemente maduro en seguridad e infraestructura
multi-tenant** para su origen (un TFG): el aislamiento por `taller_id` está bien
hecho y vigilado por un juez, la suite tiene 165 tests + CI, la auditoría de
seguridad se cerró 11/11, hay CSP con nonces y un flujo de suscripción Stripe
funcional. **Pero como PRODUCTO SaaS todavía no se puede vender a un segundo
taller**, y por dos razones concretas: (1) los PDF de presupuesto/factura llevan
**branding HARDCODEADO "AndroTech / Huelva"** (`utils/pdf_generator.py:32`), así
que el taller B emitiría documentos con el nombre y los datos de contacto del
dueño de la plataforma; (2) no existe **panel de superadmin** para operar la
plataforma (dar de alta/suspender talleres, ver MRR), ni **facturación legal**
(serie fiscal, NIF). Técnicamente, la mayor deuda es el **monolito `app.py` de
5.135 líneas** con funciones de 200–280 líneas y **0 relaciones ORM** (`models.py`),
y operativamente, **uploads efímeros + sin backups + email que no llega en el host
actual**. Madurez global: **núcleo sólido, capa de producto a medias, listo para
una demo pero no para facturar a varios clientes.**

Métricas: `app.py` 5.135 líneas · 79 rutas · 108 funciones · 44 plantillas ·
~165 tests · 0 `relationship()` en modelos · dashboard ≈ 20 consultas por carga.

---

## 1. Arquitectura y código

**🟢 Lo que está bien**
- Capa de datos limpia y aislada: `database.py` (engine perezoso, dual SQLite/PG),
  `tenancy.py` (filtro automático `with_loader_criteria` + `before_flush`), juez
  de aislamiento. Es lo mejor del proyecto.
- Módulos de dominio pequeños y cohesionados: `auth.py`, `audit.py`, `historial.py`,
  `alerts.py`, `pagination.py`, `notifications.py`, `tokens.py`. Buen tamaño.
- Migraciones idempotentes y agnósticas de motor (`migrations.py`), `server_default`
  replicando los DEFAULT — cuidado real con el dual-engine.
- Versiones pinneadas en `requirements.txt`; CI con SQLite y Postgres.

**🟡 Lo mejorable**
- **`models.py` no define NI UNA `relationship()`** (0/13 modelos). Todos los JOIN
  son manuales (`select(...).join(Cliente, ...)`), y los borrados en cascada se
  hacen a mano. Añadir relaciones + `cascade`/`passive_deletes` quitaría mucho
  boilerplate y cerraría riesgos de orfandad. **[a verificar]** que borrar un
  cliente borra/oarphana sus reparaciones de forma consistente en ambos motores
  (SQLite con FK OFF por defecto no aplica el `ON DELETE CASCADE`).
- Logging mezclado: `logger.info(json.dumps({...}))` en sitios nuevos y texto
  plano legacy. La CLAUDE.md lo admite como intencional, pero dificulta parsear.
- Duplicación: `ensure_csrf_token`/`inject_csrf_token` existen tanto en
  `utils/security.py` como redefinidas en `app.py` (L607-613) y se registran dos
  veces. `Mail(app)` se instancia (L403) pero **no se usa** para enviar (se usa
  smtplib). Restos.
- `admin_seed_demo` (262 líneas) es lógica de demo dentro del monolito de
  producción; debería ser un script/CLI, no una ruta.

**🔴 Lo que falta / preocupa**
- **Monolito `app.py` (5.135 líneas, 79 rutas)** con funciones gigantes:
  `dashboard` (276), `admin_seed_demo` (262), `stripe_webhook` (249),
  `editar_reparacion` (186), `publico_pagar` (141). Es el cuello de botella de
  mantenibilidad y el riesgo nº1 a medio plazo. El refactor a **blueprints + `create_app`
  factory (B1)** ya está identificado: hazlo antes de meter features 2026, o el
  archivo se vuelve intratable.
- No hay capa de servicios: la lógica de negocio vive en los handlers HTTP
  (validación + acceso a datos + render mezclados). Difícil de testear unitario.

---

## 2. Producto / funcionalidad (ojo de dueño de taller)

**🟢 Lo que está bien** — el ciclo básico está cubierto: alta cliente → nueva
reparación (con fotos drag&drop) → estados con máquina de transiciones
(`historial.py`) → notas internas → piezas consumidas (descuenta inventario) →
firma digital del cliente → pago online (Stripe) → ticket QR + PDF → portal de
seguimiento por código. Para un taller, **esto ya es usable**. Hay calendario,
búsqueda global, alertas (stock bajo, atrasadas) y export CSV.

**🟡 Lo mejorable**
- **Presupuesto sin aprobación del cliente**: no existe flujo para que el cliente
  apruebe/rechace un presupuesto online (grep de "aprobar" → nada). Hoy el técnico
  pone un precio y ya; falta el "OK del cliente" que evita conflictos.
- **Inventario sin proveedores ni entradas de stock**: `inventario_piezas` tiene
  `proveedor` como texto libre, pero no hay tabla de proveedores, ni órdenes de
  compra, ni historial de entradas/salidas de stock (solo se descuenta al usar).
- **Garantías**: no hay concepto de garantía por reparación (fecha fin, cobertura),
  aunque el ticket la menciona.
- **Multi-usuario por taller**: existe (usuarios + roles), pero los roles son
  globales y solo el superadmin los edita; un taller no puede ajustar permisos a
  su gente (decisión conocida, revisable).

**🔴 Lo que falta / preocupa**
- **🔴 BLOQUEANTE MULTI-TENANT: branding de los PDF hardcodeado.**
  `utils/pdf_generator.py:32` define `COMPANY = {'name':'AndroTech','address':
  'Huelva, España', phone, email, iva_rate:0.21}` y todos los documentos lo usan
  (L76, L210, L321). **El taller B emite presupuestos/facturas con el nombre,
  dirección, teléfono y email de AndroTech.** `Taller.config` (iva_rate, moneda,
  logo_url, branding) existe en el esquema **pero NUNCA se lee**. Hasta arreglar
  esto, no se puede vender a un segundo taller.
- **🔴 Facturación NO legal**: el "número de factura" es `F-{id:05d}` derivado del
  id de la reparación (`pdf_generator.py:356`), no una **serie fiscal continua**.
  No hay NIF/CIF ni razón social del taller (`Taller` no los tiene) ni del cliente
  (`Cliente` solo nombre/teléfono/email/dirección). Para cobrar de verdad en
  España hace falta serie + NIF emisor + datos fiscales del receptor.
- **Notificaciones al cliente solo por email** (`send_repair_status_update` SÍ se
  dispara en el cambio de estado, `app.py:2612` — bien), **pero el email no llega
  en producción** (Railway bloquea SMTP; sin SMS/WhatsApp el cliente no se entera).

---

## 3. Experiencia de usuario

**🟢** Rediseño visual coherente (sistema de tokens, oscuro/claro, shell con
sidebar), portal público con seguimiento animado que transmite confianza, estados
vacíos cuidados en listados.

**🟡**
- **i18n inexistente**: todo el texto está hardcodeado en español (no hay gettext).
  Si algún taller quiere catalán/inglés, no hay costura.
- Accesibilidad **[a verificar]**: el rediseño usa nonces y clases atómicas; falta
  auditar contraste AA real, foco de teclado en modales y `aria-*` en los
  componentes JS (lightbox, dropzone). No verificable estáticamente al 100%.
- Mensajes de error: mejoraron con H8 (genéricos), pero algunos siguen con emojis
  y tono inconsistente.

**🔴** Onboarding de taller nuevo casi inexistente: tras `/signup` el taller entra
a un panel **vacío** (sin datos de ejemplo opt-in, sin asistente de primeros pasos,
sin plantillas de servicios/precios). El `admin_seed_demo` existe pero es para la
demo del TFG, no un onboarding de cliente.

---

## 4. Tests y calidad

**🟢** 165 tests, juez de aislamiento permanente, reproductores de seguridad
convertidos en regresión, dual-engine (SQLite+PG), CI en cada push. Cobertura de
los caminos críticos de seguridad y aislamiento: muy buena.

**🟡 / 🔴 Zonas críticas sin test (riesgo real, no % por %):**
- **Máquina de estados `historial.py`** (`validar_transicion`): no veo tests de las
  transiciones inválidas (p. ej. saltar de Pendiente a Entregado, o un técnico
  forzando un estado no permitido). Es lógica de negocio central. **[a verificar]**
- **Generación de PDF** (`pdf_generator`): `test_pdf.py` tiene 3 tests; el cálculo de
  IVA/totales y el QR por código apenas están cubiertos.
- **Inventario/piezas**: descuento de stock al usar una pieza y devolución al
  quitarla — sin test claro de que el stock cuadra.
- **No hay tests de integración E2E** (un flujo completo cliente→pago→entrega) ni de
  **carga** (cómo responde el dashboard con miles de reparaciones).
- El test del límite de rate (H5) re-habilita el limiter pero el resto de la suite
  lo desactiva: bien para velocidad, pero **el comportamiento real del 429 + su
  handler apenas se ejercita**.

---

## 5. Preparación para producción

**🟢** `APP_ENV=production` endurece (SECRET_KEY obligatoria, cookies Secure, HSTS),
`/health` con readiness de BD, gunicorn configurado, CSP con nonces, limiter con
costura Redis (`RATELIMIT_STORAGE_URI`).

**🔴 Lo que falta para un deploy real y seguro:**
- **Uploads efímeros**: fotos y firmas se guardan en disco local
  (`UPLOADS_DIR`/`static/uploads`). En un PaaS sin volumen persistente **se pierden
  en cada redeploy**. Solución real: object storage (S3/R2) — hoy ni siquiera hay
  costura para ello (todo es `foto.save(path)` local).
- **Sin backups**: no hay script ni rutina de backup de la BD (`scripts/` no tiene
  `pg_dump`/dump). Para un SaaS con datos de clientes esto es inaceptable.
- **Cutover a Postgres pendiente** (conocido): el código está listo, la BD de prod
  no migrada.
- **Observabilidad**: Sentry es solo una costura apagada; no hay métricas (latencia,
  errores por endpoint), ni alertas, ni dashboards. Si algo falla en prod, te
  enteras por el cliente.
- **Limiter en `memory://`** por defecto: con 2+ workers no comparte contador
  (costura Redis existe, pero hay que activarla y documentar el `RATELIMIT_STORAGE_URI`).

**Escalabilidad (dónde se rompe con 50 talleres / miles de reparaciones):**
- **Dashboard**: ~20 consultas SQL en serie por carga (`app.py` función `dashboard`).
  Con tablas grandes y varios talleres concurrentes, es el primer cuello de botella.
- Listados paginados (bien), pero `audit_log` crece sin límite ni archivado
  (candidato a keyset pagination y/o retención).
- Sin caché en ningún sitio: cada carga recalcula KPIs desde cero.

---

## 6. Rendimiento

**🟢** El N+1 del historial en listados ya se eliminó (P1, consulta agregada).
Índices en `taller_id`, `(taller_id, estado)`, `cliente_id`, `codigo_publico`.

**🟡 / 🔴 Puntos calientes concretos:**
- **`app.py::dashboard`** — ~20 `text()` independientes por request (clientes,
  reparaciones, ingresos mes/total, cobrado, pendiente, top dispositivos, estados,
  últimas, atrasadas, 6× ingresos por mes en bucle, por técnico, auditoría). Cada
  uno es un round-trip. **Quick win**: agrupar en menos consultas + cachear 30–60 s.
- **`Taller.config` no cacheado** (cuando se use) y **branding/IVA recalculado**.
- Generación de PDF en proceso, síncrona, dentro del request (ticket/factura): con
  carga concurrente bloquea workers. Candidato a tarea async o cache.
- Imágenes servidas por Flask `static` sin CDN ni redimensionado (se guardan al
  tamaño original hasta 5 MB).

---

## 7. Negocio / SaaS

**🟢** Suscripción Stripe real (trial 14d, bloqueo por impago sin borrar datos,
webhook idempotente), separación de los dos flujos Stripe, gestión de la
suscripción por el taller (`/suscripcion` + Customer Portal).

**🔴 Lo que falta para operar como SaaS de verdad:**
- **Panel de SUPERADMIN inexistente**: el flag `es_superadmin` solo sirve para
  editar roles. No hay UI para **listar talleres, ver su estado/plan, suspender,
  reactivar, ver altas/bajas**. Operar la plataforma hoy es ir a la BD a mano.
- **Sin métricas de negocio**: MRR, churn, nº de talleres activos/trial,
  conversión trial→pago. Nada. No sabes cómo va el negocio.
- **Facturación legal del taller a SUS clientes** (ver §2): bloqueante para que el
  taller cobre con factura válida.
- **Emails transaccionales no fiables** (SMTP bloqueado en el host actual): falta un
  proveedor real (SendGrid/SES/Resend) por API en vez de SMTP. La costura
  `Notificador` existe; falta el backend.
- **Plan único 24,99 €**: sin tiers ni límites por plan (nº usuarios/reparaciones),
  así que no hay palanca de upsell.

---

## Tabla de oportunidades (priorizada)

| # | Oportunidad | Impacto | Esfuerzo | Categoría |
|---|---|---|---|---|
| 1 | **PDF/branding por taller** (leer `Taller.config`: nombre, dirección, NIF, IVA, logo) | 🔴 Alto | Medio | Falta (bloqueante) |
| 2 | **Email transaccional por API** (Resend/SES) en `Notificador` | Alto | Bajo | Falta |
| 3 | **Uploads a object storage (S3/R2)** + costura `storage` | Alto | Medio | Falta (prod) |
| 4 | **Backups automáticos** de la BD (pg_dump programado / snapshot gestionado) | Alto | Bajo | Falta (prod) |
| 5 | **Panel de superadmin** (listar/suspender talleres, métricas básicas) | Alto | Medio | Añadido |
| 6 | **Refactor a blueprints + `create_app`** (B1) | Alto | Alto | Mejora |
| 7 | **Facturación legal** (serie fiscal, NIF emisor/receptor, campos en `Taller`/`Cliente`) | Alto | Alto | Falta |
| 8 | **Relaciones ORM + cascadas** en `models.py` | Medio | Medio | Mejora |
| 9 | **Dashboard: agrupar consultas + caché corto** | Medio | Bajo | Mejora (perf) |
| 10 | **Aprobación de presupuesto por el cliente** (online) | Medio | Medio | Añadido |
| 11 | **Tests de `historial` (transiciones) + inventario (stock)** | Medio | Bajo | Mejora |
| 12 | **Onboarding de taller** (asistente + datos/plantillas opt-in) | Medio | Medio | Añadido |
| 13 | **Observabilidad** (activar Sentry + métricas por endpoint) | Medio | Bajo | Falta (prod) |
| 14 | **Limpiar deps muertas** (plotly, fpdf, Flask-Mail) y duplicados CSRF/Mail | Bajo | Bajo | Mejora |
| 15 | **Gestión de proveedores / entradas de stock** | Bajo-Medio | Medio | Añadido |
| 16 | **i18n** (gettext) | Bajo | Alto | Añadido |

---

## TOP 5 (lo que yo haría primero, y por qué)

1. **Branding/IVA por taller en los PDF (oportunidad #1).** Es el muro que impide
   vender a un segundo cliente: hoy sus facturas dicen "AndroTech". Es de esfuerzo
   medio (el seam `Taller.config` ya existe) y desbloquea TODO el modelo SaaS.
2. **Email transaccional por API (#2).** Sin notificaciones que lleguen, medio
   producto (seguimiento, avisos, reset) no funciona en prod. Es barato: ya hay
   `Notificador`; solo falta un backend HTTP en vez de SMTP.
3. **Persistencia de uploads + backups (#3, #4).** Hoy las fotos/firmas y, potencialmente,
   los datos, se pueden **perder**. Es inaceptable para datos de clientes y es
   esfuerzo bajo-medio. Sin esto no hay "producción".
4. **Panel de superadmin con métricas (#5).** No puedes operar ni entender el negocio
   sin ver y gestionar talleres. Habilita cobrar y dar soporte de verdad.
5. **Refactor a blueprints (#6) antes de las features 2026.** `app.py` con 5.135
   líneas y funciones de 280 ya cuesta; cada feature nueva lo empeora. Hazlo ahora
   que la suite (165 tests) te protege el refactor.

---

## Quick wins (alto/medio impacto, bajo esfuerzo)

- **Email por API** (#2): cambiar el backend de `Notificador` desbloquea avisos.
- **Backups** (#4): un `pg_dump` programado / snapshot gestionado es media tarde.
- **Dashboard** (#9): agrupar las ~20 consultas y cachear 30–60 s — mejora visible
  inmediata.
- **Limpiar deps muertas** (#14): quitar `plotly`, `fpdf` (sin uso) y `Flask-Mail`
  (instanciado y no usado), y la `validate_csrf`/`ensure_csrf_token` duplicadas en
  `app.py`. Menos superficie, build más ligero.
- **Tests de transiciones de estado** (#11): cubrir `historial.validar_transicion`
  es rápido y protege lógica central.
- **Activar Sentry** (#13): la costura ya existe; solo es poner `SENTRY_DSN`.

---

## Notas de verificación pendiente

- **[a verificar]** Borrado en cascada cliente→reparaciones en SQLite (FK OFF) y PG.
  Cómo: borrar un cliente con reparaciones y comprobar que no quedan filas huérfanas
  en ambos motores.
- **[a verificar]** Accesibilidad real (contraste AA, foco en modales, aria) del
  rediseño. Cómo: axe-core / Lighthouse sobre login, dashboard, ficha y portal.
- **[a verificar]** Que `plotly`/`fpdf`/`pillow` son realmente deps muertas. Cómo:
  `grep -ri "plotly\|fpdf\|PIL" --include=*.py` (dio vacío) y quitar una a una
  comprobando que la suite sigue verde.
