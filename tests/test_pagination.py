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
        filas_cliente = [ln for ln in body.splitlines() if "@x.com" in ln]
        assert len(filas_cliente) == n  # TODOS, no sólo page_size()

    def test_juez_contador_y_filas_scoped(self, logged_admin, db_conn):
        # Taller 1 (logueado) con 3; taller 2 con 50.
        _seed_clientes(db_conn, 1, 3, prefix="Mio")
        _crear_taller2(db_conn)
        _seed_clientes(db_conn, 2, 50, prefix="Otro")
        body = logged_admin.get("/clientes").get_data(as_text=True)
        assert "de 3" in body          # contador SOLO del taller 1 (no 53)
        assert "Otro" not in body      # jamás ve clientes del taller 2


def _seed_reparaciones(db_conn, tid, n):
    cur = db_conn.execute(
        "INSERT INTO clientes (nombre, taller_id) VALUES (?, ?)",
        (f"ClienteRep{tid}", tid))
    cid = cur.lastrowid
    for i in range(n):
        db_conn.execute(
            "INSERT INTO reparaciones (cliente_id, dispositivo, estado, "
            "fecha_entrada, precio, estado_pago, taller_id) "
            "VALUES (?, ?, 'Pendiente', ?, 100.0, 'Pendiente', ?)",
            (cid, f"Disp{i:03d}", f"2026-01-{(i % 28) + 1:02d}", tid))
    db_conn.commit()


class TestReparacionesPaginacion:
    def test_pagina_fuera_de_rango_no_rompe(self, logged_admin, db_conn):
        _seed_reparaciones(db_conn, 1, 10)
        for p in ("9999", "0", "abc", "-1"):
            assert logged_admin.get(f"/reparaciones?page={p}").status_code == 200

    def test_filtro_se_conserva_en_enlaces(self, logged_admin, db_conn):
        _seed_reparaciones(db_conn, 1, page_size() + 5)
        body = logged_admin.get("/reparaciones?estado=Pendiente").get_data(as_text=True)
        assert "estado=Pendiente&amp;page=2" in body  # el filtro viaja en los enlaces

    def test_export_csv_saca_todo_no_solo_la_pagina(self, logged_admin, db_conn):
        n = page_size() + 12
        _seed_reparaciones(db_conn, 1, n)
        r = logged_admin.get("/exportar/reparaciones.csv")
        assert r.status_code == 200
        # Filas de datos: empiezan por el id (dígito) y llevan el dispositivo
        # (excluye banner "ANDROTECH…Dispositivos" y la cabecera "…Dispositivo…").
        filas = [ln for ln in r.get_data(as_text=True).splitlines()
                 if ln[:1].isdigit() and ";Disp" in ln]
        assert len(filas) == n  # TODAS, no sólo una página

    def test_juez_contador_scoped(self, logged_admin, db_conn):
        _seed_reparaciones(db_conn, 1, 3)
        _crear_taller2(db_conn)
        _seed_reparaciones(db_conn, 2, 40)
        body = logged_admin.get("/reparaciones").get_data(as_text=True)
        assert "de 3" in body  # contador del taller 1, nunca las 43


def _seed_auditoria(db_conn, tid, n, usuario="admin"):
    for i in range(n):
        db_conn.execute(
            "INSERT INTO audit_log (taller_id, event_type, usuario, evento_datos, timestamp) "
            "VALUES (?, 'login', ?, '{}', ?)",
            (tid, usuario, f"2026-03-01 00:{i // 60:02d}:{i % 60:02d}"))
    db_conn.commit()


class TestAuditoriaPaginacion:
    def test_vista_paginada(self, logged_admin, db_conn):
        ps = page_size()
        _seed_auditoria(db_conn, 1, ps + 5)
        r1 = logged_admin.get("/admin/auditoria")
        assert r1.status_code == 200
        assert f"de {ps + 5}" in r1.get_data(as_text=True)
        assert logged_admin.get("/admin/auditoria?page=2").status_code == 200

    def test_pagina_fuera_de_rango_no_rompe(self, logged_admin, db_conn):
        _seed_auditoria(db_conn, 1, 5)
        for p in ("9999", "0", "abc"):
            assert logged_admin.get(f"/admin/auditoria?page={p}").status_code == 200

    def test_solo_admin(self, logged_tecnico, db_conn):
        r = logged_tecnico.get("/admin/auditoria", follow_redirects=False)
        assert r.status_code == 302  # redirige (no es admin)

    def test_juez_contador_scoped(self, logged_admin, db_conn):
        _seed_auditoria(db_conn, 1, 2, usuario="admin")
        _crear_taller2(db_conn)
        _seed_auditoria(db_conn, 2, 30, usuario="RIVALUSER")
        body = logged_admin.get("/admin/auditoria").get_data(as_text=True)
        assert "de 2" in body            # sólo los del taller 1
        assert "RIVALUSER" not in body   # jamás eventos del taller 2
