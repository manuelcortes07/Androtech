"""Tests de los esenciales de cuenta (B3): reset de contraseña.

Email mockeado (conftest parchea EmailService._send). Incluye el JUEZ: un reset
del taller A jamás toca a un usuario del taller B.
"""

from types import SimpleNamespace

import pytest
from itsdangerous import SignatureExpired
from werkzeug.security import check_password_hash, generate_password_hash

import tokens as account_tokens

_MSG = "te hemos enviado"  # substring del mensaje anti-enumeración


def _seed_taller_con_admin(db_conn, tid, email, password="Secreto123"):
    db_conn.execute("DELETE FROM usuarios WHERE taller_id = ?", (tid,))
    db_conn.execute("DELETE FROM talleres WHERE id = ?", (tid,))
    db_conn.execute(
        "INSERT INTO talleres (id, nombre, slug, email_contacto, fecha_alta, "
        "estado, plan) VALUES (?, ?, ?, ?, '2026-01-01', 'activo', 'basico')",
        (tid, f"Taller {tid}", f"t{tid}", email),
    )
    cur = db_conn.execute(
        'INSERT INTO usuarios (taller_id, usuario, "contraseña", rol) '
        "VALUES (?, ?, ?, 'admin')",
        (tid, "admin", generate_password_hash(password)),
    )
    db_conn.commit()
    return cur.lastrowid


def _pw_hash(db_conn, uid):
    return db_conn.execute(
        'SELECT "contraseña" FROM usuarios WHERE id = ?', (uid,)).fetchone()[0]


def _token_para(app, uid, tid, pw_hash):
    with app.test_request_context():
        return account_tokens.generar_token_reset(
            SimpleNamespace(id=uid, taller_id=tid, password=pw_hash))


class TestResetPassword:
    def test_anti_enumeracion_misma_respuesta(self, client, db_conn, monkeypatch):
        _seed_taller_con_admin(db_conn, 2, "real@x.com")
        import app as A
        enviados = []
        monkeypatch.setattr(A.email_service, "send_password_reset",
                            lambda *a, **k: enviados.append(a))
        r_existe = client.post("/reset", data={"email": "real@x.com"})
        r_no = client.post("/reset", data={"email": "noexiste@x.com"})
        # MISMA respuesta (status + mensaje genérico) exista o no el email.
        assert r_existe.status_code == r_no.status_code == 200
        assert _MSG in r_existe.get_data(as_text=True)
        assert _MSG in r_no.get_data(as_text=True)
        # Pero sólo se envía email al que SÍ existe (sin revelarlo al cliente).
        assert len(enviados) == 1

    def test_token_valido_cambia_password(self, client, db_conn, app):
        uid = _seed_taller_con_admin(db_conn, 2, "real@x.com")
        token = _token_para(app, uid, 2, _pw_hash(db_conn, uid))
        r = client.post(f"/reset/{token}", data={"password": "NuevaClave9"})
        assert r.status_code == 302
        assert check_password_hash(_pw_hash(db_conn, uid), "NuevaClave9")

    def test_token_manipulado_se_rechaza(self, client):
        r = client.get("/reset/token-falso-invalido", follow_redirects=False)
        assert r.status_code == 302
        assert "/reset" in r.headers.get("Location", "")

    def test_token_caducado_helper(self, app):
        with app.test_request_context():
            t = account_tokens.generar_token_reset(
                SimpleNamespace(id=1, taller_id=1, password="x"))
            with pytest.raises(SignatureExpired):
                account_tokens.cargar_token_reset(t, max_age=-1)

    def test_password_debil_rechazada(self, client, db_conn, app):
        uid = _seed_taller_con_admin(db_conn, 2, "real@x.com")
        token = _token_para(app, uid, 2, _pw_hash(db_conn, uid))
        r = client.post(f"/reset/{token}", data={"password": "minus"})  # débil
        assert r.status_code == 400
        # No cambió
        assert check_password_hash(_pw_hash(db_conn, uid), "Secreto123")

    def test_enlace_viejo_muere_tras_reset(self, client, db_conn, app):
        uid = _seed_taller_con_admin(db_conn, 2, "real@x.com")
        token = _token_para(app, uid, 2, _pw_hash(db_conn, uid))
        client.post(f"/reset/{token}", data={"password": "NuevaClave9"})
        # Reusar el MISMO token tras el cambio → ya no vale (huella cambió).
        r = client.get(f"/reset/{token}", follow_redirects=False)
        assert r.status_code == 302
        assert "/reset" in r.headers.get("Location", "")

    def test_aislamiento_reset_no_afecta_a_otro_taller(self, client, db_conn, app):
        # Dos talleres con la MISMA contraseña inicial.
        uid2 = _seed_taller_con_admin(db_conn, 2, "a@x.com", password="Secreto123")
        uid3 = _seed_taller_con_admin(db_conn, 3, "b@x.com", password="Secreto123")
        token2 = _token_para(app, uid2, 2, _pw_hash(db_conn, uid2))
        client.post(f"/reset/{token2}", data={"password": "ClaveDe2_9"})
        # El admin del taller 3 sigue INTACTO.
        h3 = _pw_hash(db_conn, uid3)
        assert check_password_hash(h3, "Secreto123")
        assert not check_password_hash(h3, "ClaveDe2_9")


def _login(client, tid, slug="t"):
    from auth import PERMISOS_ADMIN
    with client.session_transaction() as s:
        s["usuario"] = "admin"
        s["rol"] = "admin"
        s["permisos"] = PERMISOS_ADMIN
        s["taller_id"] = tid
        s["taller_slug"] = slug
        s["csrf_token"] = "x"


def _verificado(db_conn, tid):
    return db_conn.execute(
        "SELECT email_verificado FROM talleres WHERE id = ?", (tid,)).fetchone()[0]


class TestVerificacionEmail:
    def test_signup_envia_verificacion(self, client, db_conn, monkeypatch):
        import app as A
        import saas_billing
        monkeypatch.setattr(saas_billing, "is_configured", lambda: False)
        enviados = []
        monkeypatch.setattr(A.email_service, "send_email_verificacion",
                            lambda *a, **k: enviados.append(a))
        r = client.post("/signup", data={
            "nombre_taller": "Verifica Me", "email": "verifica@x.com",
            "usuario": "admin", "password": "Secreto123"})
        assert r.status_code == 302
        assert len(enviados) == 1  # se envió la verificación
        tid = db_conn.execute("SELECT id FROM talleres WHERE slug = ?",
                              ("verifica-me",)).fetchone()[0]
        assert _verificado(db_conn, tid) == 0  # arranca SIN verificar

    def test_enlace_activa_el_flag(self, client, db_conn, app):
        _seed_taller_con_admin(db_conn, 2, "real@x.com")
        assert _verificado(db_conn, 2) == 0
        with app.test_request_context():
            tok = account_tokens.generar_token_verificacion(2, "real@x.com")
        r = client.get(f"/verificar-email/{tok}", follow_redirects=False)
        assert r.status_code == 302
        assert _verificado(db_conn, 2) == 1

    def test_token_verificacion_manipulado(self, client, db_conn):
        _seed_taller_con_admin(db_conn, 2, "real@x.com")
        r = client.get("/verificar-email/basura", follow_redirects=False)
        assert r.status_code == 302
        assert _verificado(db_conn, 2) == 0  # sigue sin verificar

    def test_reenvio_verificacion(self, client, db_conn, monkeypatch):
        import app as A
        _seed_taller_con_admin(db_conn, 2, "real@x.com")
        _login(client, 2)
        enviados = []
        monkeypatch.setattr(A.email_service, "send_email_verificacion",
                            lambda *a, **k: enviados.append(a))
        r = client.post("/verificar-email/reenviar", follow_redirects=False)
        assert r.status_code == 302
        assert len(enviados) == 1

    def test_aislamiento_verificacion(self, client, db_conn, app):
        _seed_taller_con_admin(db_conn, 2, "a@x.com")
        _seed_taller_con_admin(db_conn, 3, "b@x.com")
        with app.test_request_context():
            tok2 = account_tokens.generar_token_verificacion(2, "a@x.com")
        client.get(f"/verificar-email/{tok2}")
        # El taller 3 NO se verifica por el enlace del taller 2.
        assert _verificado(db_conn, 2) == 1
        assert _verificado(db_conn, 3) == 0


class TestCredenciales:
    def test_cambiar_password_requiere_actual(self, client, db_conn):
        uid = _seed_taller_con_admin(db_conn, 2, "a@x.com", password="Secreto123")
        _login(client, 2)
        # Actual incorrecta → NO cambia.
        client.post("/perfil/password", data={"actual": "MALA", "nueva": "NuevaClave9"})
        assert check_password_hash(_pw_hash(db_conn, uid), "Secreto123")
        # Actual correcta → cambia.
        client.post("/perfil/password", data={"actual": "Secreto123", "nueva": "NuevaClave9"})
        assert check_password_hash(_pw_hash(db_conn, uid), "NuevaClave9")

    def test_cambiar_password_aplica_politica(self, client, db_conn):
        uid = _seed_taller_con_admin(db_conn, 2, "a@x.com", password="Secreto123")
        _login(client, 2)
        client.post("/perfil/password", data={"actual": "Secreto123", "nueva": "debil"})
        assert check_password_hash(_pw_hash(db_conn, uid), "Secreto123")  # no cambió

    def test_cambiar_email_requiere_password(self, client, db_conn):
        _seed_taller_con_admin(db_conn, 2, "viejo@x.com", password="Secreto123")
        _login(client, 2)
        client.post("/perfil/email", data={"email": "nuevo@x.com", "password": "MALA"})
        assert db_conn.execute(
            "SELECT email_contacto FROM talleres WHERE id = 2").fetchone()[0] == "viejo@x.com"

    def test_cambiar_email_redispara_verificacion(self, client, db_conn, monkeypatch):
        import app as A
        _seed_taller_con_admin(db_conn, 2, "viejo@x.com", password="Secreto123")
        db_conn.execute("UPDATE talleres SET email_verificado = 1 WHERE id = 2")
        db_conn.commit()
        _login(client, 2)
        enviados = []
        monkeypatch.setattr(A.email_service, "send_email_verificacion",
                            lambda *a, **k: enviados.append(a))
        r = client.post("/perfil/email",
                        data={"email": "nuevo@x.com", "password": "Secreto123"})
        assert r.status_code == 302
        row = db_conn.execute(
            "SELECT email_contacto, email_verificado FROM talleres WHERE id = 2").fetchone()
        assert row[0] == "nuevo@x.com" and row[1] == 0  # nuevo email, sin verificar
        assert len(enviados) == 1                       # reenvío de verificación

    def test_aislamiento_cambio_password(self, client, db_conn):
        # Mismo nombre de usuario 'admin' en dos talleres.
        uid2 = _seed_taller_con_admin(db_conn, 2, "a@x.com", password="Secreto123")
        uid3 = _seed_taller_con_admin(db_conn, 3, "b@x.com", password="Secreto123")
        _login(client, 2)  # logueado como admin del taller 2
        client.post("/perfil/password", data={"actual": "Secreto123", "nueva": "ClaveDe2_9"})
        # El admin del taller 3 (mismo nombre) queda INTACTO.
        assert check_password_hash(_pw_hash(db_conn, uid2), "ClaveDe2_9")
        assert check_password_hash(_pw_hash(db_conn, uid3), "Secreto123")
