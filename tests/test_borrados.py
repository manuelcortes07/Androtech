"""Borrados Postgres-safe (hallazgo C1 del REPASO_SALUD).

Antes: borrar una reparación con historial/piezas/notas dejaba huérfanos en
SQLite (FKs OFF) — verde en tests — y reventaba en Postgres (FKs ON) con
IntegrityError. Este test es el que FALTABA: verifica que el borrado limpia a los
hijos (0 huérfanos) y no lanza 500. En el job Postgres del CI (FKs ON) habría
fallado antes del arreglo; aquí (SQLite) demuestra que no quedan huérfanos.

Y la decisión de producto: borrar un cliente CON reparaciones se IMPIDE (no se
pierde el historial), y SIN reparaciones se permite.
"""

from tests.test_aislamiento import admin_A, dos_talleres  # noqa: F401


def _sembrar_hijos(db_conn, rep_id):
    db_conn.execute(
        "INSERT INTO reparaciones_historial (reparacion_id, estado_nuevo, "
        "fecha_cambio, usuario, taller_id) VALUES (?, 'En proceso', "
        "'2026-01-02 00:00:00', 'admin', 1)", (rep_id,))
    db_conn.execute(
        "INSERT INTO notas_reparacion (reparacion_id, usuario, contenido, "
        "fecha_creacion, taller_id) VALUES (?, 'admin', 'nota', '2026-01-02', 1)",
        (rep_id,))
    db_conn.execute(
        "INSERT INTO inventario_piezas (id, nombre, taller_id) VALUES (777, 'P', 1)")
    db_conn.execute(
        "INSERT INTO piezas_reparacion (reparacion_id, pieza_id, cantidad, "
        "fecha_uso, taller_id) VALUES (?, 777, 1, '2026-01-02', 1)", (rep_id,))
    db_conn.commit()


class TestBorrarReparacion:
    def test_borrar_con_hijos_no_revienta_ni_deja_huerfanos(self, admin_A,
                                                            dos_talleres, db_conn):
        repA = dos_talleres["repA"]  # estado_pago 'Pendiente' → borrable
        _sembrar_hijos(db_conn, repA)
        r = admin_A.get(f"/reparaciones/borrar/{repA}", follow_redirects=False)
        assert r.status_code in (302, 303)  # no 500
        assert db_conn.execute(
            "SELECT 1 FROM reparaciones WHERE id = ?", (repA,)).fetchone() is None
        for tabla in ("reparaciones_historial", "notas_reparacion",
                      "piezas_reparacion", "fotos_reparacion"):
            n = db_conn.execute(
                f"SELECT COUNT(*) FROM {tabla} WHERE reparacion_id = ?", (repA,)
            ).fetchone()[0]
            assert n == 0, f"huérfanos en {tabla}"

    def test_no_borra_reparacion_pagada(self, admin_A, dos_talleres, db_conn):
        repA = dos_talleres["repA"]
        db_conn.execute(
            "UPDATE reparaciones SET estado_pago = 'Pagado' WHERE id = ?", (repA,))
        db_conn.commit()
        admin_A.get(f"/reparaciones/borrar/{repA}", follow_redirects=False)
        assert db_conn.execute(
            "SELECT 1 FROM reparaciones WHERE id = ?", (repA,)).fetchone() is not None


class TestBorrarCliente:
    def test_impide_borrar_cliente_con_reparaciones(self, admin_A, dos_talleres,
                                                    db_conn):
        cliA = dos_talleres["cliA"]  # tiene repA
        admin_A.get(f"/clientes/borrar/{cliA}", follow_redirects=False)
        # NO se borra (se preserva el historial de reparaciones).
        assert db_conn.execute(
            "SELECT 1 FROM clientes WHERE id = ?", (cliA,)).fetchone() is not None

    def test_borra_cliente_sin_reparaciones(self, admin_A, dos_talleres, db_conn):
        db_conn.execute(
            "INSERT INTO clientes (id, nombre, taller_id) VALUES (888, 'Sin Rep', 1)")
        db_conn.commit()
        admin_A.get("/clientes/borrar/888", follow_redirects=False)
        assert db_conn.execute(
            "SELECT 1 FROM clientes WHERE id = ?", (888,)).fetchone() is None
