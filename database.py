"""SQLAlchemy engine and session — capa de acceso a datos de AndroTech.

Desde la Fase 1.9 es la ÚNICA capa de acceso: `db.py` (sqlite3 crudo)
fue eliminado y todo el proyecto usa `get_session()` + modelos de
`models.py` (o `text()` para las consultas complejas anotadas para
recibir filtro `taller_id` manual en la Fase 2).

MOTOR CONFIGURABLE (Fase 3a):
- Si `DATABASE_URL` está definida → **PostgreSQL** (driver psycopg v3).
  Railway/Heroku dan `postgres://`/`postgresql://`; se normaliza a
  `postgresql+psycopg://`.
- Si no → **SQLite** desde `DATABASE_PATH` (dev local y tests rápidos,
  comportamiento de siempre).
El resto del código es agnóstico del motor; cuando hace falta saber el
dialecto (inserts on-conflict, funciones SQL), usa `is_postgres()`.

Diseño:
- Engine y `sessionmaker` se construyen **perezosamente** en la primera
  llamada (los tests pueden cambiar `DATABASE_URL`/`DATABASE_PATH` antes).
- `Base` es la base declarativa común que extienden los modelos.
"""

from __future__ import annotations

import os
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# ───────────────────────────────────────────────────────────────────
# Resolución de la URL (Postgres si DATABASE_URL, si no SQLite)
# ───────────────────────────────────────────────────────────────────
def _resolve_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        # SQLAlchemy 2.0 + psycopg v3 requieren el scheme postgresql+psycopg://.
        # Railway/Heroku entregan postgres:// o postgresql://.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url
    path = os.environ.get("DATABASE_PATH", "database/andro_tech.db")
    return f"sqlite:///{path}"


def _es_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


# ───────────────────────────────────────────────────────────────────
# Engine + sessionmaker perezosos
# ───────────────────────────────────────────────────────────────────
_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Devuelve el `Engine` compartido, creándolo en la primera llamada."""
    global _engine
    if _engine is None:
        url = _resolve_database_url()
        if _es_sqlite(url):
            # SQLite: check_same_thread False (Flask atiende en varios threads;
            # cada Session abre y cierra su conexión).
            connect_args = {"check_same_thread": False}
            kwargs = {"connect_args": connect_args}
        else:
            # PostgreSQL (psycopg v3): client_encoding utf8 explícito para las
            # columnas con ñ (usuarios.contraseña) — pincho E. pool_pre_ping
            # evita usar conexiones muertas (Railway recicla conexiones).
            kwargs = {
                "connect_args": {"client_encoding": "utf8"},
                "pool_pre_ping": True,
            }
        _engine = create_engine(url, future=True, echo=False, **kwargs)
    return _engine


def is_postgres() -> bool:
    """True si el engine activo es PostgreSQL (para ramificar por dialecto)."""
    return get_engine().dialect.name == "postgresql"


def is_sqlite() -> bool:
    return get_engine().dialect.name == "sqlite"


def insert_or_ignore(model):
    """Devuelve un INSERT con `.on_conflict_do_nothing()` del dialecto activo.

    `sqlite_insert(...).on_conflict_do_nothing()` solo vale en SQLite y
    `postgresql_insert(...)` solo en Postgres. Este helper elige el correcto
    según el motor (pincho B de la Fase 3a). Uso:
        s.execute(insert_or_ignore(PermisoRol).values(...).on_conflict_do_nothing())
    """
    if is_postgres():
        from sqlalchemy.dialects.postgresql import insert as _pg_insert
        return _pg_insert(model)
    from sqlalchemy.dialects.sqlite import insert as _sqlite_insert
    return _sqlite_insert(model)


def get_session() -> Session:
    """Crea una nueva `Session` lista para usar con `with get_session() as s:`."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,  # los objetos siguen utilizables tras commit
            future=True,
        )
    return _SessionFactory()


# ───────────────────────────────────────────────────────────────────
# Base declarativa
# ───────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Base común para todos los modelos ORM de AndroTech."""

    pass


# ───────────────────────────────────────────────────────────────────
# Utilidad para tests / desarrollo
# ───────────────────────────────────────────────────────────────────
def reset_engine_for_tests() -> None:
    """Fuerza la recreación del engine en el próximo `get_engine()`.

    Útil si los tests cambian `DATABASE_PATH` después de que el engine
    se haya inicializado (p. ej. al saltar entre BD temporales).
    """
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
