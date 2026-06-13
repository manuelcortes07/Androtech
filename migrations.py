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
            config TEXT
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


def _anadir_taller_id_audit(conn) -> None:
    if _table_exists(conn, "audit_log") and not _has_column(conn, "audit_log", "taller_id"):
        # Nullable a propósito: eventos del superadmin de plataforma llevan NULL.
        conn.exec_driver_sql("ALTER TABLE audit_log ADD COLUMN taller_id INTEGER")


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


def aplicar_migracion_multitenant() -> dict:
    """Aplica la migración multi-tenant. Idempotente. Devuelve un resumen."""
    engine = get_engine()
    resumen = {"talleres_creada": False, "taller_1_insertado": False,
               "columnas_anadidas": [], "usuarios_rebuild": False}

    with engine.begin() as conn:
        _crear_tabla_talleres(conn)
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
        _anadir_taller_id_audit(conn)

        necesita_rebuild = (
            _table_exists(conn, "usuarios")
            and not _usuarios_tiene_unique_compuesto(conn)
        )
        _rebuild_usuarios(conn)
        resumen["usuarios_rebuild"] = necesita_rebuild

    return resumen


if __name__ == "__main__":
    import json
    print(json.dumps(aplicar_migracion_multitenant(), indent=2, ensure_ascii=False))
