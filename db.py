"""Database connection helpers."""

import sqlite3


def get_db():
    """Return a new SQLite connection with row factory set.

    The path is hardcoded to the project's database; change it if you
    relocate the file or want to make it configurable.
    """
    conn = sqlite3.connect("database/andro_tech.db")
    conn.row_factory = sqlite3.Row
    return conn
