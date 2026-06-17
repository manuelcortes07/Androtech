"""Tests de paginación server-side (B5).

Cubre: la página N trae el subconjunto correcto; los enlaces conservan la
búsqueda; el contador refleja el total FILTRADO y SCOPED; el export sigue
sacándolo TODO (no sólo la página); página fuera de rango no rompe; y EL JUEZ:
contador y filas de un taller nunca incluyen datos de otro.
"""

from pagination import page_size


def _seed_clientes(db_conn, tid, n, prefix="Cli"):
    for i in range(n):
        db_conn.execute(
            "INSERT INTO clientes (nombre, email, telefono, taller_id) "
            "VALUES (?, ?, ?, ?)",
            (f"{prefix}{i:03d}", f"{prefix}{i}@x.com", "600000000", tid),
        )
    db_conn.commit()


def _crear_taller2(db_conn):
    db_conn.execute(
        "INSERT INTO talleres (id, nombre, slug, fecha_alta, estado, plan) "
        "VALUES (2, 'B', 'b', '2026-01-01', 'activo', 'basico')")
    db_conn.commit()


class TestClientesPaginacion:
    def test_pagina_devuelve_subconjunto_correcto(self, logged_admin, db_conn):
        ps = page_size()
        _seed_clientes(db_conn, 1, ps + 5)  # dos páginas
        p1 = logged_admin.get("/clientes").get_data(as_text=True)
        p2 = logged_admin.get("/clientes?page=2").get_data(as_text=True)
        # Orden por nombre: Cli000.. → la primera va en pág 1, no en pág 2.
        assert "Cli000" in p1 and "Cli000" not in p2
        # El elemento ps (índice ps) cae en la página 2.
        assert f"Cli{ps:03d}" in p2 and f"Cli{ps:03d}" not in p1
        assert f"de {ps + 5}" in p1  # contador = total

    def test_contador_refleja_filtro(self, logged_admin, db_conn):
        _seed_clientes(db_conn, 1, 30, prefix="Alpha")
        _seed_clientes(db_conn, 1, 5, prefix="Beta")
        body = logged_admin.get("/clientes?q=Beta").get_data(as_text=True)
        assert "de 5" in body          # total del FILTRADO, no 35
        assert "Beta000" in body
        assert "Alpha000" not in body

    def test_enlaces_conservan_busqueda(self, logged_admin, db_conn):
        _seed_clientes(db_conn, 1, 40, prefix="Beta")
        body = logged_admin.get("/clientes?q=Beta").get_data(as_text=True)
        # Los enlaces de página llevan el filtro (q) además de page.
        assert "q=Beta&amp;page=2" in body

    def test_pagina_fuera_de_rango_no_rompe(self, logged_admin, db_conn):
        _seed_clientes(db_conn, 1, 10)
        for p in ("9999", "0", "abc", "-3"):
            assert logged_admin.get(f"/clientes?page={p}").status_code == 200

    def test_export_csv_saca_todo_no_solo_la_pagina(self, logged_admin, db_conn):
        n = page_size() + 17  # más de una página
        _seed_clientes(db_conn, 1, n)
        r = logged_admin.get("/exportar/clientes.csv")
        assert r.status_code == 200
        # Cada cliente sembrado tiene un email único @x.com → contamos esas filas.
        body = r.get_data(as_text=True)
        filas_cliente = [l for l in body.splitlines() if "@x.com" in l]
        assert len(filas_cliente) == n  # TODOS, no sólo page_size()

    def test_juez_contador_y_filas_scoped(self, logged_admin, db_conn):
        # Taller 1 (logueado) con 3; taller 2 con 50.
        _seed_clientes(db_conn, 1, 3, prefix="Mio")
        _crear_taller2(db_conn)
        _seed_clientes(db_conn, 2, 50, prefix="Otro")
        body = logged_admin.get("/clientes").get_data(as_text=True)
        assert "de 3" in body          # contador SOLO del taller 1 (no 53)
        assert "Otro" not in body      # jamás ve clientes del taller 2
