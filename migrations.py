"""Migración a multi-tenant (Fase 2.1).

Una única función idempotente, `aplicar_migracion_multitenant()`, que:

1. Crea la tabla `talleres` (el tenant) si no existe.
2. Inserta el taller 1 (slug "androtech") con los datos del taller real,
   si no existe.
3. Añade la columna `taller_id INTEGER NOT NULL DEFAULT 1` a las 8 tablas
   de scope que admiten ALTER TABLE simple, y `taller_id INTEGER` (nullable)
   a `audit_log` (los eventos de plataforma llevan NULL).
4. Reconstruye `usuarios` para pasar de `UNIQUE(usuario)` a
   `UNIQUE(taller_id, usuario)` — esto permite que dos talleres distintos
   tengan cada uno su propio "admin". SQLite no soporta cambiar un UNIQUE
   vía ALTER, así que se rebuildea la tabla (12-step). Es seguro: `usuarios`
   no tiene FKs entrantes, y las FKs de SQLite están OFF por defecto.

`roles` y `permisos_rol` NO se tocan (decisión de producto: roles globales).

Se invoca automáticamente en el arranque de `app.py` (tras crear las tablas
base) y también es ejecutable como script: `python migrations.py`.

Idempotencia: cada paso está guardado por comprobaciones de existencia
(`PRAGMA table_info` / `index_list`), de modo que aplicarla N veces deja
exactamente el mismo estado que aplicarla una vez.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text as _text

from database import get_engine

# Tablas que reciben `taller_id NOT NULL DEFAULT 1` vía ALTER TABLE simple.
# `usuarios` NO está aquí: se gestiona con el rebuild (necesita el UNIQUE
# compuesto, que ALTER TABLE no puede dar en SQLite).
_SCOPED_NOT_NULL = (
    "clientes",
    "reparaciones",
    "reparaciones_historial",
    "fotos_reparacion",
    "notas_reparacion",
    "piezas_reparacion",
    "inventario_piezas",
    "solicitudes_reparacion",
)

# Datos del taller real (taller 1). Coinciden con COMPANY de pdf_generator.py.
_TALLER_1 = {
    "nombre": "AndroTech",
    "slug": "androtech",
    "email_contacto": "manuelcortescontreras11@gmail.com",
    "telefono": "+34 633 234 395",
    "direccion": "Huelva, España",
}


def _table_exists(conn, table: str) -> bool:
    row = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).first()
    return row is not None


def asegurar_codigo_publico() -> None:
    """H3: garantiza `reparaciones.codigo_publico` (no adivinable) + backfill.

    Idempotente y agnóstica de motor (SQLite y Postgres). Pasos:
      1. Añade la columna si falta (SQLite: ALTER simple guardado por PRAGMA;
         Postgres: ADD COLUMN IF NOT EXISTS — o ya existe vía create_all).
      2. Backfilla las filas con código NULL/'' generando un token único.
      3. Crea un índice UNIQUE sobre la columna (CREATE UNIQUE INDEX IF NOT EXISTS).
    """
    from database import is_postgres
    from models import generar_codigo_publico

    engine = get_engine()
    with engine.begin() as conn:
        if is_postgres():
            conn.exec_driver_sql(
                "ALTER TABLE reparaciones ADD COLUMN IF NOT EXISTS codigo_publico TEXT"
            )
        else:
            if not _table_exists(conn, "reparaciones"):
                return  # esquema aún sin crear (no debería pasar en arranque)
            if not _has_column(conn, "reparaciones", "codigo_publico"):
                conn.exec_driver_sql(
                    "ALTER TABLE reparaciones ADD COLUMN codigo_publico TEXT"
                )

        # Backfill de filas sin código (NULL o vacío).
        pendientes = conn.execute(_text(
            "SELECT id FROM reparaciones "
            "WHERE codigo_publico IS NULL OR codigo_publico = ''"
        )).scalars().all()
        usados: set[str] = set()
        for rid in pendientes:
            codigo = generar_codigo_publico()
            while codigo in usados:
                codigo = generar_codigo_publico()
            usados.add(codigo)
            conn.execute(
                _text("UPDATE reparaciones SET codigo_publico = :c WHERE id = :id"),
                {"c": codigo, "id": rid},
            )

        # Índice único (tras backfill: ya no quedan NULL a colisionar).
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_reparaciones_codigo "
            "ON reparaciones (codigo_publico)"
        )


def _has_column(conn, table: str, col: str) -> bool:
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)


def _usuarios_tiene_unique_compuesto(conn) -> bool:
    """True si `usuarios` ya tiene un índice UNIQUE sobre (taller_id, usuario)."""
    for idx in conn.exec_driver_sql("PRAGMA index_list(usuarios)").fetchall():
        idx_name, unique = idx[1], idx[2]
        if not unique:
            continue
        cols = [r[2] for r in
                conn.exec_driver_sql(f"PRAGMA index_info({idx_name})").fetchall()]
        if set(cols) == {"taller_id", "usuario"}:
            return True
    return False


def _crear_tabla_talleres(conn) -> None:
    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS talleres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            email_contacto TEXT,
            telefono TEXT,
            direccion TEXT,
            fecha_alta TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'activo',
            plan TEXT NOT NULL DEFAULT 'basico',
            stripe_customer_id TEXT,
            stripe_sub_id TEXT,
            fecha_fin_periodo TEXT,
            trial_fin TEXT,
            email_verificado INTEGER NOT NULL DEFAULT 0,
            config TEXT
        )
    """)


def _anadir_columna_email_verificado(conn) -> None:
    """B3.2: talleres.email_verificado. Los talleres ya existentes se
    'grandfatherean' como verificados para no mostrarles el aviso."""
    if _table_exists(conn, "talleres") and not _has_column(conn, "talleres", "email_verificado"):
        conn.exec_driver_sql(
            "ALTER TABLE talleres ADD COLUMN email_verificado INTEGER NOT NULL DEFAULT 0")
        conn.exec_driver_sql("UPDATE talleres SET email_verificado = 1")


def _anadir_columna_trial_fin(conn) -> None:
    """Fase 3b: añade talleres.trial_fin a BD que ya tenían `talleres` sin ella."""
    if _table_exists(conn, "talleres") and not _has_column(conn, "talleres", "trial_fin"):
        conn.exec_driver_sql("ALTER TABLE talleres ADD COLUMN trial_fin TEXT")


def _crear_tabla_stripe_eventos(conn) -> None:
    """Fase 3b: ledger de idempotencia de los webhooks de suscripción del SaaS."""
    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS stripe_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            tipo TEXT,
            taller_id INTEGER,
            recibido_en TEXT NOT NULL
        )
    """)


def _insertar_taller_1(conn) -> None:
    existe = conn.exec_driver_sql(
        "SELECT 1 FROM talleres WHERE id = 1"
    ).first()
    if existe:
        return
    conn.exec_driver_sql(
        """INSERT INTO talleres
           (id, nombre, slug, email_contacto, telefono, direccion,
            fecha_alta, estado, plan)
           VALUES (1, ?, ?, ?, ?, ?, ?, 'activo', 'basico')""",
        (
            _TALLER_1["nombre"], _TALLER_1["slug"], _TALLER_1["email_contacto"],
            _TALLER_1["telefono"], _TALLER_1["direccion"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )


def _anadir_taller_id_scoped(conn) -> None:
    for tabla in _SCOPED_NOT_NULL:
        if not _table_exists(conn, tabla):
            continue  # tabla aún no creada (instalación parcial); se omite
        if not _has_column(conn, tabla, "taller_id"):
            conn.exec_driver_sql(
                f"ALTER TABLE {tabla} ADD COLUMN taller_id INTEGER NOT NULL DEFAULT 1"
            )


def _audit_tiene_unique_con_taller(conn) -> bool:
    """True si audit_log ya tiene un UNIQUE que incluye taller_id."""
    for idx in conn.exec_driver_sql("PRAGMA index_list(audit_log)").fetchall():
        idx_name, unique = idx[1], idx[2]
        if not unique:
            continue
        cols = [r[2] for r in
                conn.exec_driver_sql(f"PRAGMA index_info({idx_name})").fetchall()]
        if "taller_id" in cols:
            return True
    return False


def _rebuild_audit_log(conn) -> None:
    """Rebuild de audit_log: añade taller_id (nullable) Y mete taller_id en el
    UNIQUE → UNIQUE(taller_id, event_type, usuario, timestamp).

    Por qué el rebuild y no un simple ALTER: el UNIQUE original
    (event_type, usuario, timestamp) NO incluye taller_id, así que el "admin"
    del taller A y el "admin" del taller B que hacen login en el mismo segundo
    COLISIONAN y se pierde un evento de auditoría. Inaceptable en un log de
    seguridad multi-tenant. SQLite no permite cambiar un UNIQUE vía ALTER, de
    ahí el rebuild. Idempotente: si el UNIQUE ya incluye taller_id, no hace nada.
    """
    if not _table_exists(conn, "audit_log"):
        return
    if _audit_tiene_unique_con_taller(conn):
        return

    tiene_taller_id = _has_column(conn, "audit_log", "taller_id")

    conn.exec_driver_sql("""
        CREATE TABLE audit_log_nuevo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            taller_id INTEGER,
            event_type TEXT NOT NULL,
            usuario TEXT,
            evento_datos TEXT,
            ip_address TEXT,
            timestamp TEXT NOT NULL,
            UNIQUE(taller_id, event_type, usuario, timestamp)
        )
    """)
    if tiene_taller_id:
        conn.exec_driver_sql("""
            INSERT INTO audit_log_nuevo (id, taller_id, event_type, usuario, evento_datos, ip_address, timestamp)
            SELECT id, taller_id, event_type, usuario, evento_datos, ip_address, timestamp FROM audit_log
        """)
    else:
        conn.exec_driver_sql("""
            INSERT INTO audit_log_nuevo (id, event_type, usuario, evento_datos, ip_address, timestamp)
            SELECT id, event_type, usuario, evento_datos, ip_address, timestamp FROM audit_log
        """)
    conn.exec_driver_sql("DROP TABLE audit_log")
    conn.exec_driver_sql("ALTER TABLE audit_log_nuevo RENAME TO audit_log")
    # Recrear los índices de búsqueda.
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log(event_type)")
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC)")


def _rebuild_usuarios(conn) -> None:
    """Pasa usuarios de UNIQUE(usuario) a UNIQUE(taller_id, usuario).

    Idempotente: si ya tiene el UNIQUE compuesto, no hace nada.
    """
    if not _table_exists(conn, "usuarios"):
        return
    if _usuarios_tiene_unique_compuesto(conn):
        return

    tiene_taller_id = _has_column(conn, "usuarios", "taller_id")

    conn.exec_driver_sql("""
        CREATE TABLE usuarios_nuevo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            taller_id INTEGER NOT NULL DEFAULT 1,
            usuario TEXT NOT NULL,
            "contraseña" TEXT NOT NULL,
            rol TEXT DEFAULT 'tecnico',
            UNIQUE(taller_id, usuario)
        )
    """)

    if tiene_taller_id:
        conn.exec_driver_sql("""
            INSERT INTO usuarios_nuevo (id, taller_id, usuario, "contraseña", rol)
            SELECT id, COALESCE(taller_id, 1), usuario, "contraseña", rol
            FROM usuarios
        """)
    else:
        # Sin taller_id previo: todas las filas van al taller 1 (DEFAULT).
        conn.exec_driver_sql("""
            INSERT INTO usuarios_nuevo (id, usuario, "contraseña", rol)
            SELECT id, usuario, "contraseña", rol FROM usuarios
        """)

    conn.exec_driver_sql("DROP TABLE usuarios")
    conn.exec_driver_sql("ALTER TABLE usuarios_nuevo RENAME TO usuarios")


def _crear_tabla_taller_settings(conn) -> None:
    """Fase B6: config por taller (clave→valor, con scope). En Postgres la crea
    create_all desde el modelo TallerSetting; aquí, para SQLite."""
    conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS taller_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            taller_id INTEGER NOT NULL DEFAULT 1,
            clave TEXT NOT NULL,
            valor TEXT,
            UNIQUE(taller_id, clave)
        )
    """)


def crear_indices_rendimiento(conn) -> None:
    """Índices de rendimiento (B5), idempotentes. `taller_id` es la columna más
    caliente (toda consulta filtra por el taller); además (taller_id, estado) y
    cliente_id en reparaciones para el dashboard y los JOIN. En Postgres los
    crea `create_all` desde los modelos (index=True); aquí, para SQLite."""
    tablas_taller = list(_SCOPED_NOT_NULL) + ["usuarios", "audit_log"]
    for t in tablas_taller:
        if _table_exists(conn, t) and _has_column(conn, t, "taller_id"):
            conn.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS ix_{t}_taller_id ON {t}(taller_id)"
            )
    if _table_exists(conn, "reparaciones"):
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_reparaciones_taller_estado "
            "ON reparaciones(taller_id, estado)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_reparaciones_cliente_id "
            "ON reparaciones(cliente_id)"
        )


def aplicar_migracion_multitenant() -> dict:
    """Aplica la migración multi-tenant. Idempotente. Devuelve un resumen."""
    engine = get_engine()
    resumen = {"talleres_creada": False, "taller_1_insertado": False,
               "columnas_anadidas": [], "usuarios_rebuild": False,
               "audit_rebuild": False}

    with engine.begin() as conn:
        _crear_tabla_talleres(conn)
        _anadir_columna_trial_fin(conn)        # Fase 3b
        _anadir_columna_email_verificado(conn) # B3.2
        _crear_tabla_stripe_eventos(conn)      # Fase 3b
        resumen["talleres_creada"] = True

        antes = conn.exec_driver_sql("SELECT 1 FROM talleres WHERE id=1").first()
        _insertar_taller_1(conn)
        despues = conn.exec_driver_sql("SELECT 1 FROM talleres WHERE id=1").first()
        resumen["taller_1_insertado"] = bool(despues) and not bool(antes)

        for tabla in _SCOPED_NOT_NULL + ("audit_log",):
            tenia = _table_exists(conn, tabla) and _has_column(conn, tabla, "taller_id")
            if not tenia:
                resumen["columnas_anadidas"].append(tabla)
        _anadir_taller_id_scoped(conn)

        # audit_log: rebuild para meter taller_id en el UNIQUE (per-taller dedup).
        necesita_audit = (
            _table_exists(conn, "audit_log")
            and not _audit_tiene_unique_con_taller(conn)
        )
        _rebuild_audit_log(conn)
        resumen["audit_rebuild"] = necesita_audit

        necesita_rebuild = (
            _table_exists(conn, "usuarios")
            and not _usuarios_tiene_unique_compuesto(conn)
        )
        _rebuild_usuarios(conn)
        resumen["usuarios_rebuild"] = necesita_rebuild

        _crear_tabla_taller_settings(conn)  # B6: config por taller
        crear_indices_rendimiento(conn)  # B5: índices en taller_id y calientes

    return resumen


# ───────────────────────────────────────────────────────────────────
# Esquema defensivo SQLite (extraído del arranque de app.py en Fase 3a)
# ───────────────────────────────────────────────────────────────────
def crear_esquema_sqlite_defensivo() -> None:
    """Crea las tablas base que no crean ni `scripts/create_db.py` ni el ORM,
    con el DDL byte-idéntico al original (incluye los ON DELETE CASCADE).

    Solo para el camino SQLite. En Postgres el esquema lo crea
    `Base.metadata.create_all()` desde los modelos.
    """
    conn = get_engine().connect()
    conn.execute(_text("""
        CREATE TABLE IF NOT EXISTS fotos_reparacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reparacion_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            descripcion TEXT,
            fecha_subida TEXT NOT NULL,
            subido_por TEXT,
            FOREIGN KEY (reparacion_id) REFERENCES reparaciones(id) ON DELETE CASCADE
        )
    """))
    # Añadir columna firma si no existe (BD viejas).
    try:
        conn.execute(_text("ALTER TABLE reparaciones ADD COLUMN firma TEXT"))
        conn.commit()
    except Exception:
        pass  # columna ya existe
    conn.execute(_text("""
        CREATE TABLE IF NOT EXISTS notas_reparacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reparacion_id INTEGER NOT NULL,
            usuario TEXT NOT NULL,
            contenido TEXT NOT NULL,
            fecha_creacion TEXT NOT NULL,
            es_importante INTEGER DEFAULT 0,
            FOREIGN KEY (reparacion_id) REFERENCES reparaciones(id) ON DELETE CASCADE
        )
    """))
    conn.commit()
    conn.execute(_text("""
        CREATE TABLE IF NOT EXISTS inventario_piezas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            categoria TEXT DEFAULT 'General',
            descripcion TEXT,
            cantidad INTEGER DEFAULT 0,
            cantidad_minima INTEGER DEFAULT 5,
            precio_coste REAL DEFAULT 0,
            precio_venta REAL DEFAULT 0,
            proveedor TEXT,
            ubicacion TEXT,
            fecha_actualizacion TEXT
        )
    """))
    conn.execute(_text("""
        CREATE TABLE IF NOT EXISTS piezas_reparacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reparacion_id INTEGER NOT NULL,
            pieza_id INTEGER NOT NULL,
            cantidad INTEGER DEFAULT 1,
            fecha_uso TEXT NOT NULL,
            usuario TEXT,
            FOREIGN KEY (reparacion_id) REFERENCES reparaciones(id),
            FOREIGN KEY (pieza_id) REFERENCES inventario_piezas(id)
        )
    """))
    conn.commit()
    conn.execute(_text("""
        CREATE TABLE IF NOT EXISTS solicitudes_reparacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT NOT NULL,
            email TEXT,
            dispositivo TEXT NOT NULL,
            marca TEXT,
            modelo TEXT,
            descripcion TEXT NOT NULL,
            urgencia TEXT DEFAULT 'normal',
            fecha_preferida TEXT,
            horario_preferido TEXT,
            estado TEXT DEFAULT 'pendiente',
            notas_admin TEXT,
            fecha_solicitud TEXT NOT NULL,
            fecha_gestion TEXT
        )
    """))
    conn.commit()
    conn.close()


def asegurar_taller_1() -> bool:
    """Inserta el taller 1 ("androtech") si no existe. Dialect-agnóstico (ORM).

    Para Postgres (donde no corre el rebuild SQLite). En SQLite el taller 1 lo
    crea `aplicar_migracion_multitenant`. Devuelve True si lo insertó.
    """
    from database import get_session
    from models import Taller
    with get_session() as s:
        if s.get(Taller, 1) is not None:
            return False
        s.add(Taller(
            id=1, nombre=_TALLER_1["nombre"], slug=_TALLER_1["slug"],
            email_contacto=_TALLER_1["email_contacto"],
            telefono=_TALLER_1["telefono"], direccion=_TALLER_1["direccion"],
            fecha_alta=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            estado="activo", plan="basico",
        ))
        s.commit()
    return True


if __name__ == "__main__":
    import json
    print(json.dumps(aplicar_migracion_multitenant(), indent=2, ensure_ascii=False))
