"""Adaptador de conexión dual-engine para los tests (Fase 3a.5).

Los 66 tests usan `db_conn` con estilo sqlite3 (`?`, `cur.lastrowid`,
`row["col"]` y `row[0]`). Para correr la MISMA suite sobre Postgres sin
reescribir cada test, este adaptador envuelve la conexión DBAPI activa y:

- traduce `?` → `%s` cuando el motor es Postgres,
- a los INSERT sin RETURNING les añade `RETURNING id` para emular `lastrowid`,
- devuelve filas que soportan acceso por índice (`row[0]`) Y por clave
  (`row["col"]`), como `sqlite3.Row`.

En SQLite es un passthrough fino (sqlite3.Row ya soporta ambos accesos).
"""

from __future__ import annotations

import re
import sqlite3


class _DualRow:
    """Fila con acceso por índice y por nombre (como sqlite3.Row)."""

    __slots__ = ("_vals", "_map")

    def __init__(self, cols, vals):
        self._vals = vals
        self._map = {c: v for c, v in zip(cols, vals)}

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        return self._map[key]

    def __iter__(self):
        return iter(self._vals)

    def keys(self):
        return list(self._map.keys())


class _Result:
    """Resultado tipo cursor: fetchone/fetchall + lastrowid."""

    def __init__(self, rows, lastrowid=None):
        self._rows = rows
        self._i = 0
        self.lastrowid = lastrowid

    def fetchone(self):
        if self._i < len(self._rows):
            r = self._rows[self._i]
            self._i += 1
            return r
        return None

    def fetchall(self):
        out = self._rows[self._i:]
        self._i = len(self._rows)
        return out


_INSERT_RE = re.compile(r"^\s*INSERT\s+INTO", re.IGNORECASE)
_RETURNING_RE = re.compile(r"\bRETURNING\b", re.IGNORECASE)


class DualConn:
    """Envuelve una conexión sqlite3 o psycopg con API estilo sqlite3."""

    def __init__(self, raw, is_postgres: bool):
        self._raw = raw
        self._pg = is_postgres

    def execute(self, sql, params=()):
        if not self._pg:
            cur = self._raw.execute(sql, params)
            # sqlite3.Row ya da acceso dual; devolvemos un wrapper con lastrowid.
            rows = cur.fetchall() if cur.description else []
            return _Result(rows, getattr(cur, "lastrowid", None))

        # ── Postgres ──────────────────────────────────────────────────
        pg_sql = sql.replace("?", "%s")
        lastrowid = None
        if _INSERT_RE.match(pg_sql) and not _RETURNING_RE.search(pg_sql):
            pg_sql = pg_sql.rstrip().rstrip(";") + " RETURNING id"
        cur = self._raw.execute(pg_sql, params)
        rows = []
        if cur.description:
            cols = [d.name for d in cur.description]
            raw_rows = cur.fetchall()
            rows = [_DualRow(cols, rv) for rv in raw_rows]
            if _INSERT_RE.match(pg_sql) and rows:
                lastrowid = rows[0]["id"]
                rows = []  # el INSERT no debe exponer la fila al test
        return _Result(rows, lastrowid)

    def commit(self):
        self._raw.commit()

    def close(self):
        self._raw.close()
