# INFORME DE SEGURIDAD — AndroTech (rama `saas-migration`)

> Auditoría read-only (pentest). **No se aplicó ningún arreglo.** Se incluyen
> 4 tests reproductores (`tests/test_seguridad_auditoria.py`) que **pasan
> demostrando** los agujeros; cuando se corrija cada fallo, su reproductor
> deberá fallar (se vuelve test de regresión).

Fecha: 2026-06-20 · Alcance: `app.py`, `tenancy.py`, `auth.py`, `utils/security.py`,
`saas_billing.py`, `models.py`, plantillas y configuración.

---

## 1. Resumen ejecutivo

| Gravedad | Nº | Hallazgos |
|---|---|---|
| 🔴 Crítica | **1** | H3 |
| 🟠 Media | **3** | H1, H2, H4 |
| 🟡 Baja | **7** | H5, H6, H7, H8, H9, H10, H11 |

**Lo bien hecho (no son hallazgos, confirmado):** filtro ORM automático por
`taller_id` + JUEZ; `s.get()`/SELECT ORM con scope (IDOR **interno** cubierto);
webhook del SaaS con firma + idempotencia; `publico_pagar` valida el email del
cliente y el importe sale del servidor (sin manipulación de precio); login
acotado por taller y con rate-limit; hashing de contraseñas con werkzeug;
`SECRET_KEY` obligatoria en producción; cookies `HttpOnly`/`SameSite=Lax`/
`Secure`(prod); CSP con nonces y sin `unsafe-inline`; **autoescape de Jinja
activo, 0 `|safe`**; subida de ficheros con allowlist de extensiones (sin SVG) +
nombres aleatorios (sin path traversal) + `X-Content-Type-Options: nosniff`
→ stored-XSS mitigado; `.env` y `*.db` **no trackeados** y **sin secretos
hardcodeados** en el código.

**Titular:** el aislamiento multi-taller del núcleo ORM es sólido, pero hay
**dos superficies que se salen del modelo de aislamiento**: (1) el portal
público `/consulta?id=` expone reparaciones de **cualquier** taller a usuarios
**anónimos** (H3, 🔴), y (2) los **roles son globales pero editables** por el
admin de cualquier taller, afectando a todos (H1, 🟠). Además faltan tokens
CSRF en varias rutas que mutan estado (H2) y el webhook de reparaciones tiene un
fallback que **se salta la verificación de firma** si la librería `stripe` no
está disponible (H4).

---

## 2. Tabla de hallazgos

| ID | Área | Gravedad | Ubicación | Explotación (resumen) | Recomendación |
|----|------|----------|-----------|------------------------|----------------|
| **H3** | Exposición de datos / aislamiento | 🔴 | `app.py:3806` (`consulta`) + `tenancy.py:130-136` | Anónimo: `GET /consulta?id=N` itera el PK **global** de `reparaciones` y ve dispositivo, **nombre de cliente**, precio y estado de **cualquier taller**. Sin auth, sin rate-limit. | Ligar la consulta legacy a una prueba de propiedad (token del QR / email) o, como mínimo, no resolver el taller desde un id global enumerable; añadir rate-limit; o sustituir el id secuencial por un token opaco en el QR. |
| **H1** | Aislamiento / escalada | 🟠 (roza 🔴) | `app.py:3607/3660/3716` (`nuevo_rol`/`editar_rol`/`borrar_rol`), `auth.py` (roles globales) | Admin del **taller A** hace `POST /admin/roles/editar/<id_tecnico>` y reescribe el rol **global** `tecnico` (p. ej. le añade `usuarios_borrar`) → cambia los permisos de los técnicos de **todos** los talleres, incluido B. | Decidir el modelo: o roles **por taller** (`taller_id` en `roles`/`permisos_rol`), o **bloquear** la edición de roles de sistema/globales desde rutas de taller (sólo superadmin de plataforma). Mientras: impedir editar `es_sistema=1`. |
| **H2** | CSRF | 🟠 | `app.py:2704` (`subir_fotos`), `2736` (`eliminar_foto`), `3221` (`marcar-pagado`), `3607` (`nuevo_rol`), `3660` (`editar_rol`) | Rutas POST que mutan estado **sin** `@csrf_protect` ni validación manual. Un sitio malicioso fuerza a un usuario logueado a marcar pagos, borrar/subir fotos o **reescribir roles** (combinado con H1). | Añadir `@csrf_protect` a todas las rutas POST que mutan estado (o un `before_request` que exija CSRF en todo POST salvo webhooks). |
| **H4** | Stripe / firma webhook | 🟠 | `app.py:4749-4755` | Si `stripe` no está importable, el webhook de reparaciones **parsea el payload sin verificar firma** → un atacante forja `checkout.session.completed` y marca reparaciones como **pagadas sin pagar**. (En prod `stripe` está instalado, pero el fallback es una bomba.) | Eliminar el fallback: sin librería `stripe` o sin `STRIPE_WEBHOOK_SECRET`, **rechazar** (igual que hace el webhook del SaaS). |
| **H5** | Exposición de datos | 🟡 | `app.py:3853` (`mis_reparaciones`) | Anónimo introduce un email y ve si es cliente + sus dispositivos/precios. Acotado al taller (no cross-tenant) pero sin auth ni rate-limit → enumeración de PII por email. | Rate-limit + (idealmente) verificación por enlace/código al email antes de mostrar. |
| **H6** | Stripe / lógica | 🟡 | `app.py:4830-4843` | Webhook de reparaciones: el desajuste de importe **sólo se loguea** y marca pagado igual; sin ledger de idempotencia (a diferencia del SaaS). Re-entregas pueden duplicar emails/auditoría. | Si el importe no cuadra, **no** marcar pagado; añadir ledger de idempotencia (como `stripe_eventos`). |
| **H7** | Sesión | 🟡 | `app.py:637-665` (`login`) | No se regenera el id de sesión tras login (fixation clásica mitigada por cookies firmadas client-side de Flask). `session['permisos']` queda **obsoleto** si cambian los permisos del rol hasta re-login. | `session.clear()` antes de fijar la nueva sesión en login; recargar permisos por petición o invalidar sesiones al cambiar roles. |
| **H8** | Fuga de información | 🟡 | `app.py:4612, 4715, 3647, 1046…` (5 sitios) | `flash(f"...{str(e)}")` muestra el mensaje de excepción al usuario. | No exponer `str(e)`; mensaje genérico al usuario y traza sólo al log. |
| **H9** | Rate limiting | 🟡 | `app.py:129` (`storage_uri="memory://"`) | Limiter en memoria por-proceso: con `gunicorn --workers 2` cada worker tiene su contador (≈ doble del límite) y se resetea al reiniciar → fuerza bruta debilitada. | Backend compartido (Redis) en producción. |
| **H10** | Subida de ficheros | 🟡 | `app.py:307-308`, `2716` | La constante `MAX_CONTENT_LENGTH=5MB` por archivo **no se aplica** (sólo el límite global de 16 MB/request). La firma base64 (`guardar_firma`) no valida tamaño ni que sea PNG real. | Validar tamaño por archivo y cabecera mágica (no sólo extensión); limitar tamaño del base64 de firma. |
| **H11** | CSRF (robustez) | 🟡 | `utils/security.py:23-28` | Token CSRF por-sesión (sin rotación) y comparación con `!=` (no constante). Impacto muy bajo. | `secrets.compare_digest`; opcionalmente rotación por formulario. |

> **A verificar (no confirmado en esta pasada):** si `database/andro_tech.db`
> (con PII de clientes y hashes de contraseña) estuvo **trackeado en el
> historial git** en algún momento. En la rama actual NO está trackeado y
> `.gitignore` ya lo excluye, pero conviene revisar `git log --all -- '*.db'`
> y, si aparece, purgar el historial.

---

## 3. Reproductores creados (`tests/test_seguridad_auditoria.py`)

Los 4 PASAN hoy (demuestran el fallo). Suite total: **148/148**.

| Test | Demuestra |
|---|---|
| `TestH1...::test_admin_A_reescribe_rol_tecnico_global` | **H1**: admin del taller A reescribe el rol `tecnico` GLOBAL (efecto sobre todos los talleres). Restaura el estado al final para no contaminar la suite — el hecho de que *haga falta* restaurar ya prueba que el cambio es global. |
| `TestH2...::test_marcar_pagado_sin_csrf_token_funciona` | **H2**: `POST /reparaciones/<id>/marcar-pagado` **sin** `csrf_token` marca la reparación como pagada. |
| `TestH2...::test_contraste_ruta_protegida_rechaza_sin_csrf` | Contraste: una ruta CON `@csrf_protect` (`editar_cliente`) **no** aplica el cambio sin token → H2 es una omisión puntual, no el patrón. |
| `TestH3...::test_consulta_legacy_expone_reparacion_de_otro_taller` | **H3**: cliente **anónimo** hace `GET /consulta?id=<rep del taller B>` y recibe los datos de B (cross-taller). |

---

## 4. Plan de remediación priorizado

**Prioridad 1 — cerrar exposición/aislamiento (impacto alto, esfuerzo bajo-medio):**
1. **H3** — quitar/endurecer `/consulta?id=` (token de propiedad o id opaco) + rate-limit. *Impacto: alto. Esfuerzo: medio.*
2. **H2** — añadir `@csrf_protect` (o CSRF global en POST) a las 5 rutas. *Impacto: medio. Esfuerzo: bajo.*
3. **H4** — eliminar el fallback sin firma del webhook de reparaciones. *Impacto: medio. Esfuerzo: muy bajo.*

**Prioridad 2 — integridad multi-tenant y endurecimiento:**
4. **H1** — decidir roles por-taller vs. bloquear edición de roles de sistema desde rutas de taller. *Impacto: alto (cross-tenant). Esfuerzo: medio.*
5. **H6** — webhook de reparaciones: no marcar pagado con importe discrepante + idempotencia.
6. **H5** — rate-limit (y verificación) en `mis_reparaciones`.

**Prioridad 3 — buenas prácticas (bajo impacto):**
7. **H7** (regenerar sesión / refrescar permisos), **H8** (no filtrar `str(e)`),
   **H9** (limiter Redis en prod), **H10** (límite por-archivo + magic bytes),
   **H11** (`compare_digest`).

---

## 5. Notas de metodología

- Aislamiento: revisadas todas las `text()`, `select(Model.__table__)`,
  `exec_driver_sql` y `s.get()`. Las `__table__`/`text()` con scope llevan filtro
  manual `taller_id` correcto; `s.get()` y `select(Model)` quedan cubiertos por el
  filtro automático (`do_orm_execute` + `with_loader_criteria`). **Aviso:** el
  filtro automático sólo actúa en **SELECT** (`tenancy.py:199`); cualquier futura
  `update()`/`delete()` ORM/Core a granel **no** quedaría acotada — hoy no se usan
  (los borrados van por objeto cargado, ya scoped), pero es una trampa a vigilar.
- `sin_filtro_taller()`: sólo se usa en tests; cada uso queda auditado. OK.
- Webhooks: ambos verifican firma (el del SaaS sin fallback; el de reparaciones
  con el fallback inseguro de H4). El de reparaciones valida `taller_id` de la
  metadata contra la reparación (barrera anti-cross-taller correcta).
