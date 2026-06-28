# REPASO DE SALUD — Kintsu (saas-migration)

> Pasada de DIAGNÓSTICO tras una sesión larga (B1 blueprints, rebranding,
> white-label, notificaciones, presupuestos, panel superadmin). **No se arregló
> nada** salvo lo indicado. Fecha: 2026-06-28.

## Resumen ejecutivo

El proyecto está **sano en lo estructural**: suite **239/239 estable** (2 pasadas
seguidas, sin flakies), **0 `url_for`/`request.endpoint` rotos** (87 endpoints),
CSP sin scripts inline sin nonce y sin handlers `on*`, **0 secretos nuevos
hardcodeados**, y el aislamiento multi-tenant de las superficies nuevas
(presupuesto público, baja por token, panel superadmin) está **cubierto por
tests**. Los flujos de pago siguen atados al webhook firmado (nada marca
pagado/aprobado fuera de él).

**Pero hay un fallo serio latente para producción**: varios borrados (reparación,
cliente) **no limpian sus hijos ni tienen `ON DELETE CASCADE`** en todas las FKs.
En SQLite (FKs OFF, lo que corren los tests) esto pasa silenciosamente y los
tests quedan verdes; **en PostgreSQL (objetivo de producción) lanzará una
violación de FK y un 500**, dejando una operación básica (borrar) rota. Es el
hallazgo a atender antes del cutover a Postgres. El resto son medios/bajos.

---

## 🔴 Críticos (rompen en producción Postgres)

### C1 — Borrados sin `ON DELETE CASCADE` ni limpieza manual → fallan en Postgres
**Ubicación:**
- `blueprints/reparaciones.py:764` (`borrar_reparacion`): borra `fotos` (filas+ficheros)
  y la reparación, pero **NO** borra `notas_reparacion`, `piezas_reparacion` ni
  `reparaciones_historial`.
- `blueprints/clientes.py:354` (`borrar_cliente`): `s.delete(cliente)` sin tocar sus
  `reparaciones` (ni comprobar que existan).
- `models.py:369` (`PiezaReparacion.reparacion_id`) y `models.py:436`
  (`RepairHistorial.reparacion_id`): FK **sin** `ondelete`. `models.py:255`
  (`Reparacion.cliente_id`): FK **sin** `ondelete`. (`FotoReparacion` y
  `NotaReparacion` sí tienen `ondelete="CASCADE"`.)

**Impacto:**
- **SQLite (tests/dev, FKs OFF):** el borrado "funciona" pero deja **filas
  huérfanas** (historial/piezas apuntando a una reparación inexistente; reparaciones
  apuntando a un cliente inexistente). Por eso los tests están verdes y no lo cazan.
- **PostgreSQL (producción objetivo, FKs ON):** borrar una reparación que tenga
  historial (≈ **todas**, porque cada cambio de estado crea una fila) o piezas
  → **IntegrityError → 500**, y el borrado es imposible. Igual al borrar un cliente
  con reparaciones. Una funcionalidad básica queda rota justo al hacer el cutover.

**Recomendación:** añadir `ondelete="CASCADE"` a `PiezaReparacion.reparacion_id`,
`RepairHistorial.reparacion_id` y decidir la política de `Reparacion.cliente_id`
(¿CASCADE, o bloquear el borrado de un cliente con reparaciones?), y reflejarlo en
el esquema Postgres. **Añadir un test de borrado que corra también en Postgres**
(el dual-engine ya existe) para que el JUEZ/CI lo cace. Alternativa mínima: borrar
los hijos a mano en los handlers. Pre-existente, no introducido esta sesión, pero
agravado por el uso real (toda reparación tiene historial).

---

## 🟠 Medios

### M1 — El guardia anti-fuga white-label no cubre el email NUEVO de presupuesto
**Ubicación:** `tests/test_notificaciones.py:140` (`_CLIENTE_TEMPLATES`) lista 4
plantillas; **falta `presupuesto_enviado.html`** (email al cliente añadido esta
sesión). `TestJuezBrandingTodasLasPlantillas` tampoco lo incluye.
**Impacto:** hoy `presupuesto_enviado.html` usa `emisor.*` (verificado limpio), así
que **no hay fuga actual**. Pero el guardia anti-regresión que se creó para que
"esto no vuelva a pasar" **no protege** esa plantilla: una edición futura podría
reintroducir contacto del desarrollador sin que ningún test lo cace.
**Recomendación:** añadir `presupuesto_enviado.html` (cliente) a `_CLIENTE_TEMPLATES`
y al JUEZ de branding. (`presupuesto_respuesta_taller.html` va al taller, no al
cliente; revisarla aparte pero menor prioridad.)

### M2 — Cobertura del JUEZ en superficies nuevas: buena, con un matiz
Las superficies nuevas SÍ tienen tests de aislamiento/acceso (presupuesto:
`test_presupuestos.TestJuezPresupuesto` código-de-A-no-toca-a-B + webhook mismatch;
plataforma: 403/superadmin; baja: token firmado). **Hueco menor:** no hay un test
que confirme que el **listado del panel superadmin NO se puede ver con
`sin_filtro_taller` desde una ruta normal** (el escape sólo se usa en `plataforma.*`
tras `@superadmin_requerido`), ni un grep-test que vigile que `sin_filtro_taller`
no aparezca en blueprints no-plataforma. Es defensa-en-profundidad, no un fallo.
**Recomendación:** test "grep" que falle si `sin_filtro_taller(` aparece fuera de
`blueprints/plataforma.py`/`tenancy.py`.

---

## 🟡 Bajos

### B1 — `style=""` inline en `plataforma_suspender.html` (CSP)
**Ubicación:** `templates/plataforma_suspender.html` (1 atributo `style="max-width:560px"`).
**Impacto:** la CSP retiró `'unsafe-inline'` de `style-src`; los **atributos**
`style=` no se rehabilitan con nonce → el navegador lo **ignora** (la tarjeta no
toma el ancho máximo). Sólo cosmético, pero **rompe la regla del proyecto** "0
`style=` en plantillas". Introducido esta sesión (panel superadmin).
**Recomendación:** mover a una clase utilitaria (p. ej. `.at-card--narrow`).

### B2 — `ruff check .`: 1 error legacy
**Ubicación:** `models.py:44` `E402 Module level import not at top of file`
(`from database import Base` tras un helper). Pre-existente; el job de lint del CI
es no-bloqueante. **Recomendación:** mover el import arriba o `# noqa: E402`.

### B3 — Ledger `stripe_eventos` compartido por los dos webhooks
**Ubicación:** `blueprints/pagos.py:410` y `blueprints/suscripcion.py:368` insertan
en la misma tabla `StripeEvento` para idempotencia.
**Impacto:** los `event_id` de Stripe son únicos por cuenta; una colisión entre la
cuenta de pagos de reparaciones y la del SaaS es astronómicamente improbable. **No
es un riesgo real**, pero conviene saber que la idempotencia de ambos flujos
comparte tabla. Sin acción necesaria.

---

## ✅ Áreas SANAS (verificadas, sin hallazgos)

- **Suite/flakies:** 239/239 en 2 pasadas seguidas. El flaky del marcador "999" del
  JUEZ quedó resuelto (marcador 987654 + se eliminan nonce/csrf antes de buscar).
- **Enlaces rotos:** 0 `url_for(...)` a endpoints inexistentes y 0
  `request.endpoint == '...'` inválidos (validado contra los 87 endpoints reales).
- **Pago/Stripe:** un único punto marca `Pagado`/`aprobado` = el webhook
  `pagos.stripe_webhook`, con firma fail-closed (503), idempotencia (ledger),
  control de importe y verificación de `taller_id` de la metadata. `presupuesto_
  aprobar` sólo inicia el checkout; **no** marca aprobado por su cuenta. Los tres
  flujos (pago reparación / aprobación presupuesto / suscripción) usan endpoints,
  claves y (en suscripción) cliente Stripe separados; no se pisan.
- **Multi-tenant nuevo:** presupuesto resuelve el taller por `codigo_publico` vía
  `resolver_taller` y filtra por él; baja por token **firmado** acotado a
  (cliente, taller) del token; panel superadmin tras `@superadmin_requerido` +
  `sin_filtro_taller` **auditado**; el gate exime `plataforma.*` correctamente.
- **CSP/seguridad:** 0 `<script>` inline sin nonce, 0 handlers `on*`, sólo 1
  `style=` (B1). CSRF por defecto sigue cubriendo todo POST salvo los 2 webhooks
  (firmados). Rutas nuevas con su decorador (`@superadmin_requerido`,
  `@csrf_protect`, `@permiso_requerido`).
- **Secretos:** 0 claves/credenciales/datos personales nuevos hardcodeados; sin
  `DEBUG=True`; los errores no vuelcan `str(excepción)` a la UI (H8 vigente).
- **Migraciones:** los campos nuevos (`codigo_publico`, `nif`, `acepta_emails`,
  `presupuesto_*`, `es_superadmin`) tienen migración idempotente y ramificada por
  motor (`ADD COLUMN IF NOT EXISTS` en Postgres / guarda `_has_column` en SQLite)
  con defaults seguros.

---

## ¿Se puede romper algo en producción?

1. **SÍ, en el cutover a Postgres (C1):** borrar una reparación (con historial) o
   un cliente (con reparaciones) lanzará un 500 por violación de FK. Hoy no se nota
   porque prod aún no está en Postgres y los tests corren en SQLite con FKs OFF.
   **Es lo más importante de este informe.**
2. **Email saliente** (ya señalado en RECOMENDACIONES.md, no re-evaluado aquí):
   los presupuestos/notificaciones dependen de que el SMTP funcione en prod.
3. Todo lo demás es cosmético o defensa-en-profundidad.

## Quick wins (alto impacto / bajo esfuerzo)

1. **C1**: añadir `ondelete="CASCADE"` a las 2-3 FKs + un test de borrado dual-engine.
   (El arreglo de modelo es de minutos; el valor es enorme — evita un 500 en prod.)
2. **M1**: añadir `presupuesto_enviado.html` al guardia anti-fuga (1 línea).
3. **B1**: mover el `style=` de `plataforma_suspender.html` a una clase (1 línea).
4. **B2**: silenciar/mover el E402 de `models.py:44` para dejar `ruff check .` 100% limpio.

> Nada de esto se ha arreglado en esta pasada (modo diagnóstico). Recomiendo
> empezar por C1 antes de cualquier avance hacia el despliegue en Postgres.
