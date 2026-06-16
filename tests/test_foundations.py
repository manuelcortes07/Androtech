"""Tests de los cimientos B6: config por taller + capa de notificaciones.

Incluye el JUEZ de aislamiento para la config: un taller NO ve los ajustes de
otro (la tabla taller_settings es de scope).
"""

from flask import g

from settings import get_setting, set_setting, all_settings
from notifications import Notificador, CanalNoDisponible


# ───────────────────────── config por taller ───────────────────────────────
class TestSettings:
    def test_get_set_basico(self, app):
        with app.test_request_context("/"):
            g.taller_id = 1
            assert get_setting("horario", "cerrado") == "cerrado"  # default
            set_setting("horario", "9-18")
            assert get_setting("horario") == "9-18"

    def test_aislamiento_entre_talleres(self, app, db_conn):
        # Taller 1 fija un ajuste; el taller 2 NO debe verlo.
        with app.test_request_context("/"):
            g.taller_id = 1
            set_setting("preferencia", "VALOR_DE_1")
        with app.test_request_context("/"):
            g.taller_id = 2
            # El taller 2 ve el default, no el valor del taller 1.
            assert get_setting("preferencia", "default") == "default"
            set_setting("preferencia", "VALOR_DE_2")
            assert get_setting("preferencia") == "VALOR_DE_2"
        # Y el taller 1 sigue viendo el SUYO, intacto.
        with app.test_request_context("/"):
            g.taller_id = 1
            assert get_setting("preferencia") == "VALOR_DE_1"
            assert "VALOR_DE_2" not in all_settings().values()


# ───────────────────────── notificaciones ──────────────────────────────────
class _FakeEmail:
    def __init__(self):
        self.enviados = []

    def _send(self, *, subject, to_email, html_body, **kw):
        self.enviados.append((to_email, subject))


class TestNotificador:
    def test_canal_email_envia(self):
        fake = _FakeEmail()
        n = Notificador(email_service=fake)
        assert n.canales() == ["email"]
        ok = n.enviar("email", "cliente@x.com", "Asunto", "<b>hola</b>")
        assert ok is True
        assert fake.enviados == [("cliente@x.com", "Asunto")]

    def test_canal_no_registrado_lanza(self):
        n = Notificador(email_service=_FakeEmail())
        try:
            n.enviar("sms", "+34600", "x", "y")
            assert False, "debería haber lanzado CanalNoDisponible"
        except CanalNoDisponible:
            pass

    def test_registrar_canal_futuro(self):
        # La costura: registrar un canal nuevo sin tocar el resto.
        n = Notificador(email_service=_FakeEmail())
        recibidos = []
        n.registrar_canal("sms", lambda dest, asunto, cuerpo, **kw: recibidos.append(dest) or True)
        assert "sms" in n.canales()
        assert n.enviar("sms", "+34600", "x", "y") is True
        assert recibidos == ["+34600"]
