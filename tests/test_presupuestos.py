"""Presupuestos con aprobación del cliente.

B1: lógica pura (caducidad en lectura, importe a cobrar). Los bloques de flujo
(taller envía / cliente responde / webhook) añaden sus tests con EL JUEZ.
"""

from datetime import datetime, timedelta

import presupuestos as P


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


# Garantiza que las constantes de validez/timedelta son coherentes (no negativas).
def test_constantes_sanas():
    assert P.PRESUPUESTO_VALIDEZ_DIAS > 0
    assert 0 < P.PRESUPUESTO_SENAL_PCT <= 100
    assert P.caduca_en(datetime.now()) > datetime.now().strftime(P._FMT)
    assert isinstance(timedelta(days=P.PRESUPUESTO_VALIDEZ_DIAS), timedelta)
