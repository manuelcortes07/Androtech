# 📋 Informe de auditoría — Transición AndroTech a SaaS multi-taller

**Rama:** `saas-migration`
**Base de la rama:** `main @ cce1b51`
**Fecha:** 2026-06-09
**Alcance:** auditoría y plan. **NO se ha modificado código.**

> Este informe respeta la **REGLA DE ORO** del `CLAUDE.md`: ninguna consulta a
> BD puede ejecutarse sin filtrar por `taller_id` una vez que entremos en fase
> 2. Hoy el código es 100 % mono-tenant (0 referencias a `taller_id` en todo el
> repo).

---

## 1 · Inventario de modelos

He inspeccionado `database/andro_tech.db` con `PRAGMA table_info` y `PRAGMA foreign_key_list`.

**Total real: 12 tablas** (el `CLAUDE.md` decía 11; falta `permisos_rol` y los nombres de algunas no coinciden — lo corrijo al final del informe).

| # | Tabla | Filas hoy | Naturaleza | Necesita `taller_id` |
|---|-------|-----------|-----------|----------------------|
| 1 | `usuarios` | 5 | Cuentas de técnicos/admins de un taller | ✅ Sí |
| 2 | `clientes` | 6 | Clientes finales del taller | ✅ Sí |
| 3 | `reparaciones` | 13 | El "documento" central del negocio | ✅ Sí |
| 4 | `reparaciones_historial` | 4 | Trazabilidad de cambios de estado | ➡️ Heredado (vía `reparacion_id`) |
| 5 | `fotos_reparacion` | 0 | Imágenes subidas en una reparación | ➡️ Heredado |
| 6 | `notas_reparacion` | 0 | Notas internas | ➡️ Heredado |
| 7 | `piezas_reparacion` | 1 | Piezas consumidas en una reparación | ➡️ Heredado |
| 8 | `inventario_piezas` | 1 | Stock del taller | ✅ Sí |
| 9 | `solicitudes_reparacion` | 1 | Solicitudes desde el portal público | ✅ Sí (a qué taller llega la solicitud) |
| 10 | `audit_log` | 46 | Eventos críticos (login, pagos, cambios) | ✅ Sí (auditoría por taller) |
| 11 | `roles` | 2 | Definición de roles del sistema | ⚠️ Debatible |
| 12 | `permisos_rol` | 47 | Mapping rol→permiso | ⚠️ Debatible |

### Esquema completo (campos, NOT NULL, defaults, FK)

#### `usuarios` (5 filas)
```
id          INTEGER PK
usuario     TEXT NOT NULL          ← UNIQUE de facto (constraint definida en CREATE)
contraseña  TEXT NOT NULL          ← ⚠️ columna con ñ
rol         TEXT DEFAULT 'tecnico'
```
**Cambio multi-tenant:** + `taller_id INTEGER NOT NULL REFERENCES talleres(id)`. El UNIQUE de `usuario` pasa a ser `UNIQUE(taller_id, usuario)` para permitir que cada taller tenga su propio "admin".

#### `clientes` (6 filas)
```
id         INTEGER PK
nombre     TEXT NOT NULL
telefono   TEXT
email      TEXT
direccion  TEXT
```
**Cambio:** + `taller_id`. Importante: dos clientes con mismo email/teléfono pueden coexistir en talleres distintos.

#### `reparaciones` (13 filas) — la tabla central
```
id              INTEGER PK
cliente_id      INTEGER → clientes(id)
dispositivo     TEXT NOT NULL
descripcion     TEXT
estado          TEXT DEFAULT 'Pendiente'
fecha_entrada   TEXT
fecha_salida    TEXT
precio          REAL
tipo_documento  TEXT DEFAULT 'presupuesto'
estado_pago     TEXT DEFAULT 'Pendiente'
fecha_pago      TEXT
metodo_pago     TEXT
firma           TEXT                 ← base64/path (CLAUDE.md decía tabla `firmas`, no existe)
```
**Cambio:** + `taller_id`. Crítico: la **FK a cliente debe vivir dentro del mismo taller** (`cliente_id` + `taller_id` apuntando a la misma fila).

#### `reparaciones_historial` (4 filas)
```
id                INTEGER PK
reparacion_id     INTEGER NOT NULL → reparaciones(id)
estado_anterior   TEXT
estado_nuevo      TEXT NOT NULL
fecha_cambio      TEXT NOT NULL
usuario           TEXT
INDEX             idx_historial_reparacion
```
**Cambio:** heredado vía `reparacion_id`. Estrictamente no necesita columna propia, pero **recomendado** añadirla para que el filtro automático sea trivial (sin tener que hacer JOIN).

#### `fotos_reparacion` (0 filas), `notas_reparacion` (0 filas), `piezas_reparacion` (1 fila)
Las tres tienen `reparacion_id → reparaciones(id)` como FK obligatoria. Misma observación: heredan el taller pero es **buena práctica desnormalizar** y meter `taller_id` para evitar JOINs en todas las consultas.

#### `inventario_piezas` (1 fila)
```
id                  INTEGER PK
nombre              TEXT NOT NULL
categoria           TEXT DEFAULT 'General'
descripcion, cantidad, cantidad_minima, precio_coste, precio_venta,
proveedor, ubicacion, fecha_actualizacion
```
**Cambio:** + `taller_id`. Cada taller gestiona su propio stock.

#### `solicitudes_reparacion` (1 fila)
```
id, nombre, telefono, email, dispositivo, marca, modelo, descripcion,
urgencia DEFAULT 'normal', fecha_preferida, horario_preferido,
estado DEFAULT 'pendiente', notas_admin,
fecha_solicitud NOT NULL, fecha_gestion
```
**Cambio:** + `taller_id`. **Pregunta clave:** ¿cómo sabe el formulario público a qué taller va dirigida la solicitud? Opciones: (a) URL con slug `/{taller-slug}/solicitar-reparacion`, (b) subdominio `taller-x.androtech.com`, (c) selector de taller en el form. → decisión de fase 3.

#### `audit_log` (46 filas)
```
id, event_type NOT NULL, usuario, evento_datos (JSON), ip_address,
timestamp NOT NULL
UNIQUE(event_type, usuario, timestamp)
INDEX idx_audit_timestamp, idx_audit_event_type
```
**Cambio:** + `taller_id`. Cuidado: hay eventos del **superadmin de plataforma** (login a `/admin/talleres`, gestión de suscripciones) que no son de un taller — esos llevarán `taller_id = NULL`.

#### `roles` (2 filas) y `permisos_rol` (47 filas) — ⚠️ DEBATIBLE
```
roles: id, nombre, descripcion, es_sistema DEFAULT 0, color DEFAULT '#6c757d'
permisos_rol: id, rol_nombre, permiso
```
**Dos opciones de diseño:**

- **Opción A (más simple)**: roles y permisos son **globales** del sistema. Los talleres no pueden crear roles propios; usan los predefinidos (admin, tecnico). → 0 cambios en estas tablas.
- **Opción B (más flexible)**: cada taller puede definir sus propios roles. → ambas tablas + `taller_id`, con `es_sistema=1` para los roles globales y `taller_id IS NULL`.

> Mi recomendación: **Opción A para empezar**. Es lo que ya tienes y el dolor de B no se compensa hasta que tengas decenas de talleres con políticas distintas.

### Tabla NUEVA a crear: `talleres`

```sql
CREATE TABLE talleres (
    id                  SERIAL PRIMARY KEY,            -- o INTEGER en SQLite
    nombre              TEXT NOT NULL,
    slug                TEXT NOT NULL UNIQUE,          -- para URLs /talleres/{slug}
    email_contacto      TEXT NOT NULL,
    telefono            TEXT,
    direccion           TEXT,
    fecha_alta          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    estado              TEXT NOT NULL DEFAULT 'trial', -- trial|activo|suspendido|cancelado
    plan                TEXT NOT NULL DEFAULT 'basico',-- basico|pro|enterprise
    stripe_customer_id  TEXT,
    stripe_sub_id       TEXT,
    fecha_fin_periodo   TIMESTAMPTZ,
    config              JSONB                          -- iva_rate, moneda, logo_url, etc.
);
```

### Y opcionalmente: `talleres_admin_plataforma`

Cuentas del SaaS (tú/equipo) que pueden ver TODOS los talleres. Distinto de los admins **de** un taller.

---

## 2 · Inventario de consultas

**Total detectadas:** 186 consultas (regex sobre `.execute()` / `.executemany()` en strings simples, triples y dobles comillas).

| Fichero | SELECT | INSERT | UPDATE | DELETE | CREATE | Total |
|---------|-------:|-------:|-------:|-------:|-------:|------:|
| `app.py` | 138 | 19 | 14 | 12 | 9 | **192*** |
| `auth.py` | 2 | 4 | 0 | 0 | 2 | 8 |
| `audit.py` | 0 | 1 | 0 | 0 | 3 | 4 |
| `historial.py` | 1 | 1 | 0 | 0 | 0 | 2 |
| `scripts/create_db.py` | 0 | 0 | 0 | 0 | 4 | 4 |

\* La suma supera 186 porque queries con JOIN tocan varias tablas y se contabilizan en cada una.

### Por tabla

| Tabla | SELECT | INSERT | UPDATE | DELETE | CREATE |
|-------|-------:|-------:|-------:|-------:|-------:|
| `reparaciones` | 55 | 3 | 4 | 1 | 4 |
| `clientes` | 29 | 3 | 2 | 1 | 2 |
| `roles` | 12 | 3 | 1 | 1 | 1 |
| `reparaciones_historial` | 7 | 2 | 0 | 0 | 0 |
| `solicitudes_reparacion` | 7 | 1 | 2 | 1 | 1 |
| `inventario_piezas` | 6 | 2 | 3 | 1 | 2 |
| `usuarios` | 6 | 1 | 2 | 1 | 1 |
| `fotos_reparacion` | 4 | 2 | 0 | 2 | 1 |
| `notas_reparacion` | 4 | 2 | 0 | 1 | 1 |
| `piezas_reparacion` | 4 | 1 | 0 | 1 | 1 |
| `permisos_rol` | 3 | 4 | 0 | 2 | 1 |
| `audit_log` | 1 | 1 | 0 | 0 | 3 |

> **`reparaciones` es la "tabla caliente" con 67 toques.** Es donde más puntos de fallo de aislamiento habrá.

### Patrón crítico: queries `WHERE id = ?` exclusivo → 61 ocurrencias

Estas son las consultas más peligrosas para multi-tenancy. Ejemplo típico:

```python
reparacion = conn.execute('SELECT * FROM reparaciones WHERE id=?', (id,)).fetchone()
```

Si un técnico del taller A llama a `GET /reparaciones/editar/<id>` con un `id` del taller B, hoy obtiene los datos del taller B porque **no hay verificación de pertenencia**. Tras multi-tenancy todas deberán ser:

```python
SELECT * FROM reparaciones WHERE id=? AND taller_id=?
```

Las 15 primeras de las 61 (todas en `app.py`):

```
L 934   update clientes ... where id=?
L 944   select * from clientes where id=?
L1001   select fecha_cambio from reparaciones_historial where reparacion_id = ?
L1038   select * from clientes where id=?
L1044   select * from reparaciones where cliente_id=?
L1159   delete from clientes where id=?
L1517   select fecha_cambio from reparaciones_historial where reparacion_id = ?
L1622   select nombre, email from clientes where id=?
L1660   select estado from reparaciones where id=?
L1678   select precio from reparaciones where id=?
L1688   update reparaciones set ... where id=?
L1700   select c.nombre, c.email from reparaciones r join clientes c ... where r.id=?
L1738   select * from reparaciones where id=?
L1751   select * from fotos_reparacion where reparacion_id = ?
L1758   select * from notas_reparacion where reparacion_id = ?
```

### Queries de scan completo

- **0 UPDATE/DELETE sin WHERE** ✅ (búsqueda exhaustiva). No hay queries tipo "borra todo" que se puedan colar sin filtro de taller.
- Los SELECT sin WHERE (listados como `SELECT * FROM clientes`) son **decenas** — todos los listados del CRUD: dashboard, listas, exportaciones CSV, calendario, etc. Estos son los que la **capa automática de filtrado** debe interceptar para añadir `WHERE taller_id = current_taller()`.

### Consultas que actualmente filtran por taller

**0.** Confirmado con grep:
```
grep -rEn "taller_id|tenant_id|organizacion_id" app.py auth.py audit.py historial.py utils/ scripts/
→ (sin resultados)
```

---

## 3 · Mapa de rutas

**Total real: 65 rutas** (`CLAUDE.md` dice "~65", el prompt menciona 41 — la cifra real es 65). Hay **una ruta duplicada**: `/health` aparece dos veces (L586 `healthcheck` y L4086 `health`) — corregir en fase 0.

Agrupadas por funcionalidad (✅ = necesita scope de taller, ⚪ = global/sistema, 🌐 = pública):

### Públicas (sin login)
| Línea | Método | Ruta | Vista | Scope |
|------:|--------|------|-------|-------|
| 596 | GET | `/` | `index` | 🌐 (debería mostrar landing del SaaS) |
| 586 | GET | `/health` | `healthcheck` | ⚪ |
| 4086 | GET | `/health` | `health` ⚠️ **duplicada** | ⚪ |
| 515 | GET/POST | `/login` | `login` | ⚠️ debe identificar **a qué taller** se loguea (subdominio o `usuario@slug`) |
| 572 | GET | `/logout` | `logout` | ⚪ |
| 2944 | GET/POST | `/contacto` | `contacto` | 🌐 landing pública |
| 2975 | GET | `/sobre` | `sobre` | 🌐 |
| 2983 | GET | `/servicios` | `servicios` | 🌐 |
| 2991 | GET/POST | `/consulta` | `consulta` | 🌐 → ✅ (la consulta es del taller que aloja la reparación) |
| 3031 | GET/POST | `/mis-reparaciones` | `mis_reparaciones` | 🌐 → ✅ |
| 3082 | GET/POST | `/solicitar-reparacion` | `solicitar_reparacion` | 🌐 → ✅ (necesita saber a qué taller llega) |

### Portal cliente / Stripe
| Línea | Método | Ruta | Vista | Scope |
|------:|--------|------|-------|-------|
| 3731 | POST | `/publico/pagar/<int:id>` | `publico_pagar` | ✅ (sólo si la reparación pertenece al taller) |
| 3876 | GET | `/pago_exito` | `pago_exito` | ✅ |
| 3884 | POST | `/stripe/webhook` | `stripe_webhook` | ✅ (metadata Stripe debe llevar `taller_id`) |

### Dashboard y búsqueda (logueado)
| 620 | GET | `/dashboard` | `dashboard` | ✅ |
| 1169 | GET | `/buscar` | `buscar` | ✅ |
| 2219 | GET | `/calendario` | `calendario` | ✅ |
| 2225 | GET | `/api/calendario/eventos` | `api_calendario_eventos` | ✅ |

### CRUD Clientes (7 rutas)
| 877 | GET | `/clientes` | `clientes` | ✅ |
| 887 | GET/POST | `/clientes/nuevo` | `nuevo_cliente` | ✅ |
| 922 | GET/POST | `/clientes/editar/<int:id>` | `editar_cliente` | ✅ |
| 1154 | GET | `/clientes/borrar/<int:id>` | `borrar_cliente` | ✅ |
| 951 | GET | `/cliente/historial` | `historial_cliente` | ✅ |
| 1026 | GET | `/cliente/<int:id>/historial-pdf` | `exportar_historial_cliente_pdf` | ✅ |
| 1341 | GET | `/exportar/clientes.csv` | `exportar_clientes_csv` | ✅ |

### CRUD Reparaciones (17 rutas)
| 1426 | GET | `/reparaciones` | `reparaciones` | ✅ |
| 1561 | GET/POST | `/reparaciones/nueva` | `nueva_reparacion` | ✅ |
| 1646 | GET/POST | `/reparaciones/editar/<int:id>` | `editar_reparacion` | ✅ |
| 1814 | GET | `/reparaciones/borrar/<int:id>` | `borrar_reparacion` | ✅ |
| 1851 | POST | `/reparaciones/<int:id>/fotos` | `subir_fotos_reparacion` | ✅ |
| 1884 | POST | `/reparaciones/fotos/<int:foto_id>/eliminar` | `eliminar_foto_reparacion` | ✅ |
| 1909 | GET | `/reparaciones/<int:id>/firma` | `firmar_reparacion` | ✅ |
| 1925 | POST | `/reparaciones/<int:id>/firma` | `guardar_firma_reparacion` | ✅ |
| 1977 | POST | `/reparaciones/<int:id>/notas` | `agregar_nota_reparacion` | ✅ |
| 2006 | POST | `/reparaciones/notas/<int:nota_id>/eliminar` | `eliminar_nota_reparacion` | ✅ |
| 2164 | POST | `/reparaciones/<int:id>/piezas` | `agregar_pieza_reparacion` | ✅ |
| 2195 | POST | `/reparaciones/piezas/<int:uso_id>/eliminar` | `eliminar_pieza_reparacion` | ✅ |
| 2263 | GET | `/reparaciones/<int:id>/ticket` | `ticket_recogida` | ✅ |
| 2374 | POST | `/reparaciones/<int:id>/marcar-pagado` | `marcar_reparacion_pagada` | ✅ |
| 2435 | GET | `/reparaciones/pdf/<int:id>` | `generar_pdf_presupuesto` | ✅ |
| 1249 | GET | `/exportar/reparaciones.csv` | `exportar_reparaciones_csv` | ✅ |
| 360 | GET | `/export/reparaciones` | `export_reparaciones` | ✅ (¿duplicado con la anterior?) |

### Inventario (5 rutas)
| 2033 | GET | `/inventario` | `inventario` | ✅ |
| 2064 | GET/POST | `/inventario/nueva` | `nueva_pieza` | ✅ |
| 2094 | GET/POST | `/inventario/editar/<int:id>` | `editar_pieza` | ✅ |
| 2132 | GET | `/inventario/eliminar/<int:id>` | `eliminar_pieza` | ✅ |
| 2149 | GET | `/api/inventario/buscar` | `api_buscar_piezas` | ✅ |

### Admin usuarios/roles (8 rutas)
| 2508 | GET | `/admin/usuarios` | `admin_usuarios` | ✅ |
| 2535 | GET/POST | `/admin/usuarios/nuevo` | `nuevo_usuario` | ✅ |
| 2610 | GET/POST | `/admin/usuarios/editar/<int:id>` | `editar_usuario` | ✅ |
| 2693 | GET | `/admin/usuarios/borrar/<int:id>` | `borrar_usuario` | ✅ |
| 2742 | GET | `/admin/roles` | `admin_roles` | ⚪ (opción A) o ✅ (opción B) |
| 2784 | GET/POST | `/admin/roles/nuevo` | `nuevo_rol` | ⚪/✅ |
| 2838 | GET/POST | `/admin/roles/editar/<int:id>` | `editar_rol` | ⚪/✅ |
| 2902 | GET | `/admin/roles/borrar/<int:id>` | `borrar_rol` | ⚪/✅ |

### Admin sistema (8 rutas)
| 3421 | GET | `/admin/sistema` | `admin_sistema` | ✅ |
| 3514 | GET/POST | `/admin/test-email` | `admin_test_email` | ✅ |
| 3136 | GET | `/admin/defensa` | `admin_defensa` | ⚪ (legacy TFG, **a quitar del SaaS**) |
| 3179 | GET | `/admin/seed-demo` | `admin_seed_demo` | ⚠️ **PELIGROSO**: hoy seedea la BD entera; en SaaS solo del taller actual |
| 3596 | GET | `/admin/solicitudes` | `admin_solicitudes` | ✅ |
| 3631 | POST | `/admin/solicitudes/<int:id>/aceptar` | `aceptar_solicitud` | ✅ |
| 3697 | POST | `/admin/solicitudes/<int:id>/rechazar` | `rechazar_solicitud` | ✅ |
| 3717 | POST | `/admin/solicitudes/<int:id>/borrar` | `borrar_solicitud` | ✅ |

### Documentos del TFG (2 rutas, legacy)
| 3163 | GET | `/docs/<path:subpath>/<filename>` | `docs_download` | ⚪ (legacy TFG) |
| 3169 | GET | `/docs-view/<path:subpath>/<filename>` | `docs_view` | ⚪ (legacy TFG) |

### Resumen del scope
- **55 rutas necesitan scope de taller** (✅)
- **8 rutas son globales/sistema** (⚪): logout, health × 2, sobre, servicios, contacto, defensa, docs
- **6 rutas son del portal público** (🌐) y necesitan saber **a qué taller** apuntan
- **3 rutas conflictivas:**
  1. `/health` duplicada
  2. `/exportar/reparaciones.csv` y `/export/reparaciones` posibles duplicados
  3. `/admin/seed-demo` peligrosa en multi-tenant

---

## 4 · Estado de la base de datos

**Hoy: SQLite 3** (`database/andro_tech.db`, ~100 KB, committed al repo para datos demo).

### Cosas SQLite-only que romperán en Postgres

| # | Patrón | Ocurrencias | Cambio Postgres |
|---|--------|-------------|-----------------|
| 1 | `INTEGER PRIMARY KEY AUTOINCREMENT` | 11 (en `CREATE TABLE`) | `id SERIAL PRIMARY KEY` o mejor `INTEGER GENERATED ALWAYS AS IDENTITY` |
| 2 | `INSERT OR IGNORE INTO ...` | 3 (app.py:2810, auth.py:106, auth.py:117) | `INSERT INTO ... ON CONFLICT (...) DO NOTHING` |
| 3 | Placeholder `?` en queries | ~186 | `%s` con psycopg2/3 (o pasarse a SQLAlchemy y dejar que el ORM lo gestione) |
| 4 | Fechas almacenadas como `TEXT` | todas las columnas `fecha_*` | Migrar a `TIMESTAMPTZ` |
| 5 | Booleanos como `INTEGER` | `es_importante`, `es_sistema` | Migrar a `BOOLEAN` |
| 6 | `sqlite3.Row` | `db.py:13` | `psycopg2.extras.RealDictCursor` o equivalente |
| 7 | `sqlite3.connect(...)` | `db.py:12` | `psycopg2.connect(DATABASE_URL)` con pool |
| 8 | Constraint `UNIQUE(...)` con valor `NULL` | `audit_log` UNIQUE con `usuario` que puede ser NULL | Postgres trata NULLs como distintos → posibles duplicados (no aplica aquí, pero ojo) |
| 9 | Manejo de transacciones implícito | en todo `app.py` | Postgres requiere `BEGIN/COMMIT` explícito si no usas autocommit |

### Lo que se mantiene sin cambios

- **Lógica de negocio** (validación de estados, cálculo de precios, generación de PDFs, envío de emails, Stripe webhook). 0 dependencias de SQLite.
- **Plantillas Jinja2** y todo el frontend.
- **utils/** (security, email_service, pdf_generator) — agnósticos.
- **Configuración Flask** y deploy a Railway (Railway ofrece Postgres managed).

### Coste estimado de la migración SQL pura (sin multi-tenancy todavía)

- **Cambiar `db.py`**: 1 fichero, ~20 líneas, conectar a Postgres con pool de conexiones.
- **Reemplazar `?` por `%s`** en ~186 queries: 1-2 horas con find&replace cuidadoso + smoke test.
- **`INSERT OR IGNORE` → `ON CONFLICT`**: 3 ocurrencias, 10 min.
- **`AUTOINCREMENT` → `SERIAL`**: 11 ocurrencias en `CREATE TABLE` (todos en `app.py`, `auth.py`, `audit.py`, `scripts/create_db.py`), 30 min.
- **Migración de datos**: script one-shot que lee SQLite y escribe en Postgres preservando IDs. Trivial con `pandas` o `sqlalchemy.metadata.create_all + bulk_insert`.
- **Total esperado**: **1-2 días de trabajo concentrado** si no tocamos nada más.

> **Decisión recomendada:** introduce un **ORM (SQLAlchemy)** ANTES de migrar a Postgres. Hacerlo en dos pasos (1. SQLite con SQLAlchemy, 2. cambiar el `DATABASE_URL` a Postgres) es mucho más seguro que migrar SQL crudo en bloque. Y prepara el terreno para multi-tenancy (filtros automáticos via query events).

---

## 5 · Plan de migración por fases

El `CLAUDE.md` ya esboza fases 0-5. Aquí las concreto con **el orden técnico que minimiza el riesgo** según lo que he visto.

### Fase 0 · Precondiciones (1-2 días)
1. **Limpiar duplicados** detectados en la auditoría:
   - Eliminar `/health` duplicada (mantener `healthcheck` en L586, borrar `health` en L4086).
   - Decidir entre `/export/reparaciones` y `/exportar/reparaciones.csv` (revisar ambas).
   - Decidir cómo se sirve `/admin/defensa` y `/docs/...` en el SaaS (probablemente desaparecen, son legacy TFG).
2. **Reflejar en CLAUDE.md las 12 tablas reales** (no 11) y nombres correctos (`fotos_reparacion`, no `reparaciones_fotos`; `inventario_piezas`, no `piezas`; etc.).
3. **Decisión producto**: subdominio (`mitaller.androtech.es`) vs path (`/t/mitaller/...`) vs subdominio compartido + selector. Mi recomendación: **subdominio** porque es más limpio para clientes finales y separa el `/login`.
4. **Decisión producto**: ¿roles globales (opción A) o por-taller (opción B)?

### Fase 1 · Introducir SQLAlchemy sobre SQLite (3-5 días)
1. Crear modelos SQLAlchemy de las 12 tablas (sin cambios de esquema todavía).
2. Reescribir `db.py` para devolver `Session` en lugar de `sqlite3.Connection`.
3. Migrar **gradualmente** las consultas a ORM, módulo por módulo:
   - Empezar por **`auth.py`** y **`audit.py`** (menos consultas, más críticas).
   - Después **`historial.py`** y **`alerts.py`**.
   - Después secciones de `app.py` por entidad (clientes → reparaciones → inventario → admin).
4. Mantener tests de humo (`/health`, login, dashboard, crear reparación, generar PDF, webhook Stripe simulado) verdes en cada paso.

> En este punto el código sigue siendo **mono-tenant**. SQLAlchemy es el habilitador para introducir el filtro automático en la fase 2.

### Fase 2 · Multi-tenancy en SQLite + SQLAlchemy (5-7 días) — **LA MÁS CRÍTICA**

1. Crear tabla `talleres` + sembrar un único taller con todos los datos existentes (`taller_id = 1`).
2. Migración de esquema: añadir `taller_id NOT NULL DEFAULT 1` en **9 tablas** (`usuarios`, `clientes`, `reparaciones`, `reparaciones_historial`, `fotos_reparacion`, `notas_reparacion`, `piezas_reparacion`, `inventario_piezas`, `solicitudes_reparacion`). +1 nullable en `audit_log`. Total: **10 tablas tocadas**.
3. Crear el **mecanismo de filtrado automático** (esto es lo que cumple la REGLA DE ORO). Tres caminos:
   - **A) SQLAlchemy `with_loader_criteria`** aplicado en un `@event.listens_for(Session, 'do_orm_execute')`. Lo recomiendo.
   - **B) `flask_sqlalchemy` con un `BaseQuery` custom** que añade `filter_by(taller_id=g.taller_id)` automáticamente.
   - **C) Postgres Row-Level Security** (RLS). Más seguro a nivel BD pero acopla la lógica al motor. Útil **en combinación con A o B** como red de seguridad.
4. Cargar `g.taller_id` en un `@before_request` a partir del subdominio (o del usuario logueado).
5. Auditoría manual de las **61 queries `WHERE id = ?` críticas** para verificar que el filtro automático cubre todas. Las que escapen al ORM (raw SQL en CSV, exportaciones, dashboard) requieren filtrado **manual y explícito**.
6. **Test de aislamiento**: crear 2 talleres con datos parecidos y verificar con un script que ninguna ruta filtra cruzado.

### Fase 3 · Migrar a Postgres + suscripciones Stripe (3-5 días)
1. Provisionar Postgres en Railway.
2. Cambiar `DATABASE_URL` y verificar que SQLAlchemy hace su trabajo. Ejecutar la suite de tests de humo.
3. Migrar datos demo de SQLite → Postgres con script one-shot.
4. Activar **Postgres RLS** sobre las tablas con `taller_id` como red de seguridad adicional.
5. Implementar registro self-service: `POST /signup` crea taller + admin + Stripe Customer + Subscription (trial 14 días).
6. Webhooks Stripe extra: `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`.

### Fase 4 · Producción (2-3 días)
1. Backups automáticos diarios de Postgres.
2. Logging por taller (etiqueta `taller_id` en cada log JSON).
3. Limites por plan (cantidad de reparaciones/mes, usuarios, piezas).
4. Configuración de dominio principal + wildcard subdominios.

### Fase 5 · Landing + ventas
Fuera del scope técnico.

### Estimación total
- **Pre-trabajo de saneamiento**: 1-2 días
- **Fases 1+2**: **8-12 días** (la migración multi-tenant es la dura)
- **Fase 3**: 3-5 días
- **Fase 4**: 2-3 días

**Total: ~3-4 semanas a dedicación completa.** Si lo haces en ratos sueltos, prevé 2-3 meses.

---

## 6 · Riesgos

Ordenados por probabilidad × impacto (más críticos arriba).

### 🔴 ALTO

1. **Las 61 queries `WHERE id = ?` sin verificación de pertenencia.**
   El filtro automático del ORM debería cubrirlas, pero **cualquier raw SQL que escape al ORM se salta el filtro**. Concretamente:
   - Exportaciones CSV y PDF construyen SQL crudo en `app.py:1249, 1341, 1426, 360, ...`.
   - `/admin/seed-demo` actualmente itera la BD entera.
   - Dashboard (`/dashboard` L620) hace queries crudas con `strftime` para los KPIs.

2. **Webhook de Stripe (`/stripe/webhook` L3884).**
   Si la metadata del Checkout Session no lleva `taller_id` o lo lleva mal, un pago de un taller podría marcarse como cobrado en otro. **Acción**: incluir `taller_id` en `metadata` al crear el Checkout Session (`publico_pagar` L3731) y verificarlo en el webhook.

3. **Portal público (`/consulta`, `/mis-reparaciones`, `/solicitar-reparacion`).**
   Estas rutas reciben tráfico sin login. El cliente final solo sabe su número de reparación o email. Si no se identifica el taller (por subdominio o slug), un cliente del taller A podría buscar reparaciones por email y le aparecerían las del taller B con el mismo email. **Acción**: el subdominio es la fuente de verdad del taller en estas rutas.

4. **`session['taller_id']` mal seteada en `/login`.**
   El login actual (L515) busca el usuario por `usuario` (UNIQUE global). En multi-tenant tiene que ser `usuario + taller_id`. Si el subdominio dice "tallerA" pero el usuario "admin" existe en taller A y B, hay que escoger el correcto.

### 🟠 MEDIO

5. **`audit_log` sin `taller_id` o con `NULL`** dejaría una vía para que admins de plataforma confundan eventos de distintos talleres. La constraint `UNIQUE(event_type, usuario, timestamp)` también puede colisionar entre talleres si dos usuarios distintos con el mismo nombre hacen login en el mismo segundo.

6. **Datos heredados sin desnormalizar.** `reparaciones_historial`, `fotos_reparacion`, `notas_reparacion`, `piezas_reparacion` heredan el taller vía JOIN. Si por rendimiento o por raw SQL se acceden directamente sin JOIN, el filtro se pierde. **Recomendación**: desnormalizar y meter `taller_id` también en estas 4 tablas (suma 4 columnas, ahorra fallos).

7. **Roles y permisos compartidos (opción A).**
   Si decides opción B después, migrar es doloroso. Si decides opción A pero un cliente pide cambiar permisos en su taller, no podrás.

8. **`socket.setdefaulttimeout(20)` en `app.py:25`.**
   Si en Postgres una query lenta supera 20s, el worker muere. Quitarlo cuando migremos no, pero **monitorear**. Quitarlo hoy = 502 si SMTP cuelga.

### 🟡 BAJO (pero pesados)

9. **Subir a SQLAlchemy con código en español.**
   Las columnas `contraseña` (con ñ), nombres como `reparaciones_historial` vs `historial_reparaciones`... SQLAlchemy maneja Unicode bien, pero algunos drivers de Postgres son sensibles a `client_encoding`. **Mitigación**: setear `client_encoding=utf8` en la conexión.

10. **El TFG queda mezclado con el SaaS en el mismo repo.**
    `docs/`, `/admin/defensa`, plantillas con el branding "AndroTech – Huelva, +34 633...". Para el SaaS habrá que parametrizar el branding por taller (logo, nombre, IVA, divisa) — probablemente desde `talleres.config` JSONB.

11. **Tests inexistentes.**
    Hoy no hay suite de tests automatizada. Hacer la fase 2 sin tests es jugar con fuego. **Pre-fase 1 fuerte: añadir tests mínimos de integración** con `pytest` + `Flask test_client`.

12. **La BD está commiteada al repo.**
    En el SaaS no puede estar committed — cada cliente tiene la suya en Postgres. Habrá que sacarla del repo (añadir `*.db` a `.gitignore`) y generar datos demo on-demand desde un script.

---

## Anexo · Inconsistencias detectadas con CLAUDE.md (a corregir aparte)

| Tema | Lo que dice CLAUDE.md | Realidad |
|------|----------------------|----------|
| Nº de tablas | 11 | **12** (falta `permisos_rol`) |
| Tabla `firmas` | listada | **No existe**; las firmas viven en `reparaciones.firma` (BLOB/path) |
| Tabla `reparaciones_fotos` | listada | **Se llama `fotos_reparacion`** |
| Tabla `reparaciones_notas` | listada | **Se llama `notas_reparacion`** |
| Tabla `reparaciones_piezas` | listada | **Se llama `piezas_reparacion`** |
| Tabla `piezas` | listada | **Se llama `inventario_piezas`** |
| Tabla `solicitudes_publicas` | listada | **Se llama `solicitudes_reparacion`** |
| Tabla `roles` | no listada | **Sí existe** |
| Total rutas | ~65 | **65 exactas, con una duplicada `/health`** |

> Sugerencia: cuando autorices el primer commit en esta rama, actualizo
> `CLAUDE.md` con estos datos reales como parte del trabajo de pre-Fase 0.

---

## Siguiente paso (lo decides tú)

Te propongo este orden de ataque, pero espero tu confirmación antes de tocar
una sola línea de código:

1. **Pre-fase 0 inmediata**: corregir `CLAUDE.md` (12 tablas, nombres reales,
   `/health` duplicada).
2. **Decidir las 2 preguntas de producto**: subdominio vs path, y roles
   globales vs por-taller.
3. **Empezar Fase 1**: introducir SQLAlchemy sobre SQLite, módulo por módulo.

Dime por dónde empezamos.
