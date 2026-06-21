"""Tests de la pasada de pulido (P1 N+1, P2 notificaciones, P3 CSP nonces)."""

from flask import g

import app as A
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


# ───────────────────────── P4: huecos de cobertura ──────────────────────────
def _seed_reparacion(db_conn, tid):
    cur = db_conn.execute(
        "INSERT INTO reparaciones (dispositivo, estado, taller_id) "
        "VALUES ('iPhone', 'Pendiente', ?)", (tid,))
    db_conn.commit()
    return cur.lastrowid


class TestSubidaFoto:
    def test_subir_foto_multipart(self, logged_admin, db_conn):
        import io
        rid = _seed_reparacion(db_conn, 1)
        data = {'fotos': (io.BytesIO(b'\x89PNG\r\n\x1a\n fake png'), 'foto.png')}
        r = logged_admin.post(f"/reparaciones/{rid}/fotos", data=data,
                              content_type='multipart/form-data')
        assert r.status_code == 302
        n = db_conn.execute(
            "SELECT COUNT(*) FROM fotos_reparacion WHERE reparacion_id = ?",
            (rid,)).fetchone()[0]
        assert n == 1

    def test_juez_no_sube_a_reparacion_de_otro_taller(self, logged_admin, db_conn):
        import io
        # Reparación del taller 2; el admin del taller 1 NO debe poder subirle fotos.
        db_conn.execute(
            "INSERT INTO talleres (id, nombre, slug, fecha_alta, estado, plan) "
            "VALUES (2, 'B', 'b', '2026-01-01', 'activo', 'basico')")
        rid2 = _seed_reparacion(db_conn, 2)
        data = {'fotos': (io.BytesIO(b'fake'), 'x.png')}
        logged_admin.post(f"/reparaciones/{rid2}/fotos", data=data,
                          content_type='multipart/form-data')
        n = db_conn.execute(
            "SELECT COUNT(*) FROM fotos_reparacion WHERE reparacion_id = ?",
            (rid2,)).fetchone()[0]
        assert n == 0  # no se subió nada a la reparación del taller 2


class TestFirmaBase64:
    def test_guardar_firma(self, logged_admin, db_conn):
        import base64
        rid = _seed_reparacion(db_conn, 1)
        # H10: PNG con cabecera mágica REAL (8 bytes) + datos.
        png = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'firma-real').decode()
        r = logged_admin.post(
            f"/reparaciones/{rid}/firma",
            json={"firma": f"data:image/png;base64,{png}"},
            headers={"X-CSRFToken": "test-csrf-token"})
        assert r.status_code == 200
        firma = db_conn.execute(
            "SELECT firma FROM reparaciones WHERE id = ?", (rid,)).fetchone()[0]
        assert firma and firma.startswith(f"firma_{rid}_")

    def test_firma_rechaza_csrf_invalido(self, logged_admin, db_conn):
        rid = _seed_reparacion(db_conn, 1)
        r = logged_admin.post(f"/reparaciones/{rid}/firma",
                              json={"firma": "data:image/png;base64,AAAA"},
                              headers={"X-CSRFToken": "MALO"})
        assert r.status_code == 403


class TestCSVContenido:
    def test_clientes_csv_contiene_los_datos(self, logged_admin, db_conn):
        db_conn.execute(
            "INSERT INTO clientes (nombre, email, telefono, direccion, taller_id) "
            "VALUES ('Juan Test', 'juan@test.com', '600123456', 'Calle 1', 1)")
        db_conn.commit()
        body = logged_admin.get("/exportar/clientes.csv").get_data(as_text=True)
        assert "Juan Test" in body
        assert "juan@test.com" in body
        assert "600123456" in body

    def test_reparaciones_csv_contiene_dispositivo_y_estado(self, logged_admin, db_conn):
        cur = db_conn.execute(
            "INSERT INTO clientes (nombre, taller_id) VALUES ('Cli X', 1)")
        cid = cur.lastrowid
        db_conn.execute(
            "INSERT INTO reparaciones (cliente_id, dispositivo, estado, precio, taller_id) "
            "VALUES (?, 'Samsung S99', 'Terminado', 199.0, 1)", (cid,))
        db_conn.commit()
        body = logged_admin.get("/exportar/reparaciones.csv").get_data(as_text=True)
        assert "Samsung S99" in body
        assert "Terminado" in body
