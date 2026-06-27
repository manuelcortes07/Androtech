"""Presupuestos con aprobación del cliente.

B1: lógica pura (caducidad en lectura, importe a cobrar). Los bloques de flujo
(taller envía / cliente responde / webhook) añaden sus tests con EL JUEZ.
"""

from datetime import datetime, timedelta

import presupuestos as P
from tests.test_aislamiento import admin_A, dos_talleres  # noqa: F401
from tests.test_notificaciones import captura_email  # noqa: F401


class TestHelpersPuros:
    def test_caduca_en_por_defecto_7_dias(self):
        base = datetime(2026, 1, 1, 12, 0, 0)
        assert P.caduca_en(base) == "2026-01-08 12:00:00"
        assert P.caduca_en(base, dias=3) == "2026-01-04 12:00:00"

    def test_esta_caducado(self):
        ahora = datetime(2026, 1, 10, 12, 0, 0)
        assert P.esta_caducado("2026-01-09 12:00:00", ahora) is True   # pasado
        assert P.esta_caducado("2026-01-11 12:00:00", ahora) is False  # futuro
        assert P.esta_caducado(None, ahora) is False                   # sin fecha
        assert P.esta_caducado("basura", ahora) is False               # ilegible

    def test_estado_efectivo_caduca_solo_si_enviado(self):
        ahora = datetime(2026, 1, 10, 12, 0, 0)
        pasado = "2026-01-01 00:00:00"
        futuro = "2026-02-01 00:00:00"
        assert P.estado_efectivo("enviado", pasado, ahora) == "caducado"
        assert P.estado_efectivo("enviado", futuro, ahora) == "enviado"
        # Un presupuesto ya respondido NO caduca aunque pase la fecha.
        assert P.estado_efectivo("aprobado", pasado, ahora) == "aprobado"
        assert P.estado_efectivo("rechazado", pasado, ahora) == "rechazado"
        assert P.estado_efectivo(None, pasado, ahora) is None

    def test_puede_responder(self):
        assert P.puede_responder("enviado") is True
        for e in ("caducado", "aprobado", "rechazado", "cambios_solicitados", None):
            assert P.puede_responder(e) is False

    def test_importe_a_cobrar_total_por_defecto(self):
        assert P.importe_a_cobrar(120.0) == 120.0
        assert P.importe_a_cobrar(120.0, pct=30) == 36.0
        assert P.importe_a_cobrar(0) == 0.0
        assert P.importe_a_cobrar(None) == 0.0


def test_migracion_anade_columnas(db_conn):
    """La migración idempotente dejó las columnas de presupuesto en reparaciones.
    Motor-agnóstico: un SELECT de las 5 columnas falla si alguna no existe."""
    db_conn.execute(
        "SELECT presupuesto_estado, presupuesto_enviado_en, presupuesto_caduca_en, "
        "presupuesto_respondido_en, presupuesto_comentario_cliente "
        "FROM reparaciones WHERE 1=0"
    ).fetchall()


class TestEnviarPresupuesto:
    """B2 — el taller envía el presupuesto: fija estado/validez y dispara el email
    transaccional white-label del taller dueño."""

    def test_enviar_fija_estado_y_caducidad(self, admin_A, dos_talleres,
                                            captura_email, db_conn):
        repA = dos_talleres["repA"]  # precio 100.0, cliente con email
        nombre_A = db_conn.execute(
            "SELECT nombre FROM talleres WHERE id = 1"
        ).fetchone()["nombre"]
        r = admin_A.post(f"/reparaciones/{repA}/presupuesto/enviar",
                         data={"csrf_token": "tk"}, follow_redirects=False)
        assert r.status_code in (302, 303)
        row = db_conn.execute(
            "SELECT presupuesto_estado, presupuesto_enviado_en, presupuesto_caduca_en "
            "FROM reparaciones WHERE id = ?", (repA,)
        ).fetchone()
        assert row["presupuesto_estado"] == "enviado"
        assert row["presupuesto_enviado_en"]
        assert row["presupuesto_caduca_en"] > row["presupuesto_enviado_en"]
        # Email transaccional al cliente, white-label del taller A (no B='Rival').
        assert captura_email.get("enviado") is True
        html = captura_email.get("html", "")
        assert nombre_A in html
        assert "Rival" not in html

    def test_sin_precio_no_envia(self, admin_A, dos_talleres, db_conn,
                                 captura_email):
        repA = dos_talleres["repA"]
        db_conn.execute("UPDATE reparaciones SET precio = NULL WHERE id = ?", (repA,))
        db_conn.commit()
        admin_A.post(f"/reparaciones/{repA}/presupuesto/enviar",
                     data={"csrf_token": "tk"}, follow_redirects=False)
        estado = db_conn.execute(
            "SELECT presupuesto_estado FROM reparaciones WHERE id = ?", (repA,)
        ).fetchone()["presupuesto_estado"]
        assert estado is None  # no se marcó enviado sin precio
        assert "enviado" not in captura_email


# Garantiza que las constantes de validez/timedelta son coherentes (no negativas).
def test_constantes_sanas():
    assert P.PRESUPUESTO_VALIDEZ_DIAS > 0
    assert 0 < P.PRESUPUESTO_SENAL_PCT <= 100
    assert P.caduca_en(datetime.now()) > datetime.now().strftime(P._FMT)
    assert isinstance(timedelta(days=P.PRESUPUESTO_VALIDEZ_DIAS), timedelta)
