"""Database connection helpers."""

import os
import sqlite3

# Permitir override por variable de entorno (necesario para la batería de
# tests, que monta una BD temporal limpia). Si no se define, cae al valor
# por defecto del proyecto.
DEFAULT_DB_PATH = "database/andro_tech.db"


def _resolve_db_path():
    return os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)


def get_db():
    """Return a new SQLite connection with row factory set.

    Lee la ruta desde la variable de entorno `DATABASE_PATH` en cada llamada
    (no se cachea), de forma que los tests puedan apuntar a una BD distinta
    sin reiniciar el proceso.
    """
    conn = sqlite3.connect(_resolve_db_path())
    conn.row_factory = sqlite3.Row
    return conn
