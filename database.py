"""SQLAlchemy engine and session — capa de acceso a datos de AndroTech.

Desde la Fase 1.9 es la ÚNICA capa de acceso: `db.py` (sqlite3 crudo)
fue eliminado y todo el proyecto usa `get_session()` + modelos de
`models.py` (o `text()` para las consultas complejas anotadas para
recibir filtro `taller_id` manual en la Fase 2).

Diseño:
- Engine y `sessionmaker` se construyen **perezosamente** en la primera
  llamada. Esto permite que los tests modifiquen `DATABASE_PATH` antes del
  primer uso, y que durante el desarrollo se cambie la BD sin reiniciar
  el intérprete.
- La ruta sale del mismo `DATABASE_PATH` que usa `db.py` para que las dos
  capas apunten siempre al mismo fichero SQLite.
- `Base` es la base declarativa común que extienden los modelos en
  `models.py`.

Cuando lleguemos a Fase 3 (Postgres), solo cambia la URL del engine; el
resto del código permanece igual.
"""

from __future__ import annotations

import os
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# ───────────────────────────────────────────────────────────────────
# Resolución de la URL
# ───────────────────────────────────────────────────────────────────
def _resolve_database_url() -> str:
    """Construye la URL SQLAlchemy a partir de la misma ruta que usa db.py.

    Mantener la lógica aquí (y no importar `_resolve_db_path` desde db.py)
    evita un acoplamiento innecesario; ambos leen la misma variable.
    """
    path = os.environ.get("DATABASE_PATH", "database/andro_tech.db")
    # En Windows con ruta absoluta SQLAlchemy necesita 3 slashes adicionales
    # tras "sqlite://", pero para rutas relativas (lo habitual) basta con 3.
    return f"sqlite:///{path}"


# ───────────────────────────────────────────────────────────────────
# Engine + sessionmaker perezosos
# ───────────────────────────────────────────────────────────────────
_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Devuelve el `Engine` compartido, creándolo en la primera llamada."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            _resolve_database_url(),
            future=True,
            echo=False,
            # SQLite tiene check_same_thread por defecto en True. Como Flask
            # puede atender requests en threads distintos, lo desactivamos
            # — cada Session abre su propia conexión y la cierra.
            connect_args={"check_same_thread": False},
        )
    return _engine


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
