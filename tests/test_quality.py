"""Tests de la pasada de pulido (P1 N+1, P2 notificaciones, P3 CSP nonces)."""

import app as A
from flask import g

from database import get_session


# ───────────────────────── P1: N+1 → consulta agregada ─────────────────────
class TestUltimasActualizaciones:
    def test_devuelve_el_maximo(self, app, db_conn):
        cur = db_conn.execute(
            "INSERT INTO reparaciones (dispositivo, estado, taller_id) "
            "VALUES ('X', 'Pendiente', 1)")
        rid = cur.lastrowid
        db_conn.execute(
            "INSERT INTO reparaciones_historial (reparacion_id, estado_nuevo, "
            "fecha_cambio, taller_id) VALUES (?, 'Pendiente', '2026-01-01 10:00:00', 1)", (rid,))
        db_conn.execute(
            "INSERT INTO reparaciones_historial (reparacion_id, estado_nuevo, "
            "fecha_cambio, taller_id) VALUES (?, 'Terminado', '2026-02-01 12:00:00', 1)", (rid,))
        db_conn.commit()
        with app.test_request_context():
            g.taller_id = 1
            with get_session() as s:
                res = A._ultimas_actualizaciones(s, [rid])
        # MAX == la entrada más reciente (idéntico a ORDER BY DESC LIMIT 1).
        assert res[rid] == "2026-02-01 12:00:00"

    def test_vacio_sin_ids(self, app):
        with app.test_request_context():
            g.taller_id = 1
            with get_session() as s:
                assert A._ultimas_actualizaciones(s, []) == {}

    def test_juez_scoped_por_taller(self, app, db_conn):
        # Misma reparacion_id "intrusa" con una fila de taller 2 más reciente.
        db_conn.execute(
            "INSERT INTO reparaciones_historial (reparacion_id, estado_nuevo, "
            "fecha_cambio, taller_id) VALUES (999, 'X', '2026-01-01 00:00:00', 1)")
        db_conn.execute(
            "INSERT INTO reparaciones_historial (reparacion_id, estado_nuevo, "
            "fecha_cambio, taller_id) VALUES (999, 'X', '2030-01-01 00:00:00', 2)")
        db_conn.commit()
        with app.test_request_context():
            g.taller_id = 1
            with get_session() as s:
                res = A._ultimas_actualizaciones(s, [999])
        # NO ve la fila (más nueva) del taller 2.
        assert res.get(999) == "2026-01-01 00:00:00"


# ───────────────────────── P2: notificaciones centralizadas ─────────────────
class TestNotificacionesCentralizadas:
    def test_enviar_email_delega_al_emailservice(self, app, monkeypatch):
        llamadas = []
        monkeypatch.setattr(A.email_service, "send_test",
                            lambda *a, **k: llamadas.append((a, k)))
        with app.app_context():
            A.notificador.enviar_email("send_test", "x@y.com", "Nombre")
        assert llamadas == [(("x@y.com", "Nombre"), {})]

    def test_call_site_de_reset_pasa_por_notificador(self, client, db_conn, monkeypatch):
        from werkzeug.security import generate_password_hash
        db_conn.execute(
            "INSERT INTO talleres (id, nombre, slug, email_contacto, fecha_alta, "
            "estado, plan) VALUES (2, 'B', 'b', 'real@x.com', '2026-01-01', 'activo', 'basico')")
        db_conn.execute(
            'INSERT INTO usuarios (taller_id, usuario, "contraseña", rol) '
            "VALUES (2, 'admin', ?, 'admin')", (generate_password_hash("x"),))
        db_conn.commit()
        capt = []
        monkeypatch.setattr(A.notificador, "enviar_email",
                            lambda metodo, *a, **k: capt.append(metodo))
        client.post("/reset", data={"email": "real@x.com"})
        # El envío salió por el punto único (notificador), no por email_service.
        assert "send_password_reset" in capt
