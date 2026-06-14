"""Migración de datos SQLite → PostgreSQL (Fase 3a.4).

Copia TODAS las filas de la BD SQLite de AndroTech a un PostgreSQL,
preservando exactamente los `id`, hashes de contraseña, timestamps y
`taller_id` — y reseteando las secuencias de Postgres al final para que el
próximo INSERT no choque con un id ya existente (pincho C).

Qué hace, en orden:
  1. Construye el esquema en Postgres DESDE LOS MODELOS
     (`Base.metadata.create_all`, pincho F) — nunca el rebuild de 12 pasos
     de SQLite.
  2. Copia tabla por tabla en orden FK-seguro (`metadata.sorted_tables`),
     con los `id` explícitos (no autogenerados).
  3. Resetea cada secuencia a MAX(id) (pincho C).
  4. Verifica que el nº de filas coincide tabla por tabla.

Pincho D (tipos lógicos): los modelos sólo usan Text/Integer/Float — las
fechas son TEXT y los booleanos (es_sistema, es_importante) son INTEGER en
AMBOS motores. La copia es valor-a-valor, sin conversión, así que el tipo
lógico se conserva.

USO (este script NO toca producción por sí solo; tú le das la URL destino):

    # BD origen: SQLite por DATABASE_PATH (default database/andro_tech.db)
    # BD destino: la URL Postgres que le pases con --target

    python scripts/migrate_sqlite_to_postgres.py \
        --source database/andro_tech.db \
        --target "postgresql://user:pass@localhost:5432/androtech" \
        --fresh        # opcional: DROP + recrea el esquema destino antes

Sin `--fresh`, el destino debe estar vacío (si tiene filas, aborta para no
duplicar). El esquema siempre se asegura vía create_all (idempotente).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys

# El script vive en scripts/; añadimos la raíz del repo al path para importar
# los módulos de la app (database, models).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text


def _normalizar_url_pg(url: str) -> str:
    """postgres:// / postgresql:// → postgresql+psycopg:// (psycopg v3)."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def migrar(source_path: str, target_url: str, fresh: bool = False) -> int:
    # Importamos modelos para poblar Base.metadata. database.Base es la misma
    # base declarativa que extienden todos los modelos.
    import models  # noqa: F401  (registra las tablas en el metadata)
    from database import Base

    if not os.path.exists(source_path):
        print(f"✗ BD origen no encontrada: {source_path}", file=sys.stderr)
        return 1

    target_url = _normalizar_url_pg(target_url)
    pg = create_engine(
        target_url,
        future=True,
        connect_args={"client_encoding": "utf8"},  # pincho E (ñ en contraseña)
    )
    if pg.dialect.name != "postgresql":
        print(f"✗ El destino no es PostgreSQL: {target_url}", file=sys.stderr)
        return 1

    # ── 1. Esquema destino desde los modelos (pincho F) ──────────────────
    if fresh:
        print("→ --fresh: DROP de todas las tablas en el destino…")
        Base.metadata.drop_all(pg)
    Base.metadata.create_all(pg)
    print("✓ Esquema asegurado en Postgres (create_all desde modelos).")

    # ── Origen: SQLite crudo (lectura simple, sin ORM ni filtros) ────────
    src = sqlite3.connect(source_path)
    src.row_factory = sqlite3.Row

    tablas = list(Base.metadata.sorted_tables)  # orden FK-seguro
    nombres_origen = {
        r[0] for r in src.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    total_filas = 0
    resumen = []  # (tabla, n)

    with pg.begin() as conn:
        # ── Pre-chequeo: destino vacío (salvo --fresh) ───────────────────
        if not fresh:
            no_vacias = []
            for t in tablas:
                n = conn.execute(
                    text(f'SELECT COUNT(*) FROM "{t.name}"')
                ).scalar()
                if n:
                    no_vacias.append((t.name, n))
            if no_vacias:
                detalle = ", ".join(f"{n}={c}" for n, c in no_vacias)
                print(
                    f"✗ El destino NO está vacío ({detalle}). Usa --fresh para "
                    "recrearlo o vacíalo manualmente. Aborto para no duplicar.",
                    file=sys.stderr,
                )
                return 1

        # ── 2. Copia tabla por tabla, ids explícitos ─────────────────────
        for t in tablas:
            if t.name not in nombres_origen:
                print(f"  · {t.name}: no existe en origen, salto.")
                resumen.append((t.name, 0))
                continue

            filas = src.execute(f'SELECT * FROM "{t.name}"').fetchall()
            if not filas:
                resumen.append((t.name, 0))
                continue

            # Sólo columnas que existen en AMBOS lados (defensivo).
            cols_modelo = [c.name for c in t.columns]
            cols_origen = set(filas[0].keys())
            cols = [c for c in cols_modelo if c in cols_origen]

            ins = t.insert()
            datos = [{c: fila[c] for c in cols} for fila in filas]
            conn.execute(ins, datos)

            total_filas += len(filas)
            resumen.append((t.name, len(filas)))
            print(f"  · {t.name}: {len(filas)} filas.")

        # ── 3. Reset de secuencias (pincho C) ────────────────────────────
        # Tras insertar ids explícitos, la secuencia SERIAL sigue en 1; hay que
        # adelantarla a MAX(id) para que el próximo INSERT dé MAX(id)+1.
        for t in tablas:
            if "id" not in t.columns:
                continue
            # setval(seq, COALESCE(max,1), max IS NOT NULL):
            #   - tabla vacía → setval(seq,1,false) → siguiente nextval = 1
            #   - con filas   → setval(seq,max,true) → siguiente nextval = max+1
            conn.execute(text(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{t.name}', 'id'),
                    COALESCE((SELECT MAX(id) FROM "{t.name}"), 1),
                    (SELECT MAX(id) FROM "{t.name}") IS NOT NULL
                )
                """
            ))
        print("✓ Secuencias reseteadas a MAX(id) (pincho C).")

    # ── 4. Verificación de conteos origen vs destino ─────────────────────
    print("\n── Verificación de filas (origen SQLite vs destino Postgres) ──")
    ok = True
    with pg.connect() as conn:
        for t in tablas:
            if t.name not in nombres_origen:
                continue
            n_src = src.execute(
                f'SELECT COUNT(*) FROM "{t.name}"'
            ).fetchone()[0]
            n_dst = conn.execute(
                text(f'SELECT COUNT(*) FROM "{t.name}"')
            ).scalar()
            estado = "✓" if n_src == n_dst else "✗ DESAJUSTE"
            if n_src != n_dst:
                ok = False
            print(f"  {estado}  {t.name}: origen={n_src}  destino={n_dst}")

    src.close()

    if not ok:
        print("\n✗ Hay desajustes de conteo. Revisa antes de usar el destino.",
              file=sys.stderr)
        return 1

    print(f"\n✓ Migración completa: {total_filas} filas en "
          f"{len([r for r in resumen if r[1]])} tablas con datos.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Migra datos SQLite → PostgreSQL.")
    ap.add_argument(
        "--source",
        default=os.environ.get("DATABASE_PATH", "database/andro_tech.db"),
        help="Ruta de la BD SQLite origen (default: DATABASE_PATH o "
             "database/andro_tech.db).",
    )
    ap.add_argument(
        "--target",
        default=os.environ.get("TARGET_DATABASE_URL", ""),
        help="URL del PostgreSQL destino (o env TARGET_DATABASE_URL).",
    )
    ap.add_argument(
        "--fresh", action="store_true",
        help="DROP + recrea el esquema destino antes de copiar.",
    )
    args = ap.parse_args()

    if not args.target:
        ap.error("Falta --target (URL Postgres destino) o env TARGET_DATABASE_URL.")

    return migrar(args.source, args.target, fresh=args.fresh)


if __name__ == "__main__":
    raise SystemExit(main())
