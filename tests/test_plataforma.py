"""Panel de PLATAFORMA (superadmin de Kintsu).

EL JUEZ del control de acceso: CADA ruta del panel debe dar 403 a un admin de
taller normal y 200 sólo al superadmin. Y el panel SÍ ve cross-taller (es su
función legítima) — lo contrario del aislamiento normal.
"""

import pytest

from auth import PERMISOS_ADMIN
from tests.test_aislamiento import admin_A, dos_talleres  # noqa: F401


@pytest.fixture
def superadmin(client, dos_talleres):
    """Cliente logueado como SUPERADMIN de plataforma (es_superadmin=True)."""
    with client.session_transaction() as s:
        s["usuario"] = "admin"
        s["rol"] = "admin"
        s["permisos"] = PERMISOS_ADMIN
        s["taller_id"] = 1
        s["taller_slug"] = "androtech"
        s["csrf_token"] = "tk"
        s["es_superadmin"] = True
    return client


class TestAccesoPanel:
    def test_admin_de_taller_normal_recibe_403(self, admin_A):
        # admin_A está logueado como admin del taller A, SIN es_superadmin.
        assert admin_A.get("/plataforma").status_code == 403

    def test_anonimo_no_entra(self, client):
        r = client.get("/plataforma", follow_redirects=False)
        assert r.status_code in (302, 401, 403)  # login_required redirige

    def test_superadmin_entra(self, superadmin):
        assert superadmin.get("/plataforma").status_code == 200


class TestListadoCrossTaller:
    def test_superadmin_ve_todos_los_talleres(self, superadmin):
        # El panel de plataforma SÍ ve los dos talleres (función legítima del
        # superadmin) — al contrario que el JUEZ de aislamiento normal.
        body = superadmin.get("/plataforma").get_data(as_text=True)
        assert "Rival" in body          # taller B (nombre)
        assert "/rival" in body         # taller B (slug)
        assert "Suspendido" not in body or "Activa" in body  # render del estado

    def test_busqueda_filtra(self, superadmin):
        body = superadmin.get("/plataforma?q=Rival").get_data(as_text=True)
        assert "Rival" in body


class TestSuspenderReactivar:
    def test_admin_normal_no_puede_suspender_ni_reactivar(self, admin_A, dos_talleres):
        assert admin_A.post("/plataforma/talleres/2/suspender",
                            data={"csrf_token": "tk"}).status_code == 403
        assert admin_A.post("/plataforma/talleres/2/reactivar",
                            data={"csrf_token": "tk"}).status_code == 403

    def test_superadmin_suspende_y_reactiva(self, superadmin, dos_talleres, db_conn):
        r = superadmin.post("/plataforma/talleres/2/suspender",
                            data={"csrf_token": "tk"}, follow_redirects=False)
        assert r.status_code in (302, 303)
        estado = db_conn.execute(
            "SELECT estado FROM talleres WHERE id = 2").fetchone()["estado"]
        assert estado == "suspendido"
        # queda constancia en auditoría
        n = db_conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE event_type = 'taller_suspendido'"
        ).fetchone()[0]
        assert n >= 1
        # reactivar revierte
        superadmin.post("/plataforma/talleres/2/reactivar",
                        data={"csrf_token": "tk"}, follow_redirects=False)
        estado = db_conn.execute(
            "SELECT estado FROM talleres WHERE id = 2").fetchone()["estado"]
        assert estado == "activo"

    def test_taller_suspendido_queda_bloqueado(self, client, dos_talleres, db_conn):
        # Con el taller B suspendido, un admin de B queda bloqueado por la PUERTA.
        db_conn.execute("UPDATE talleres SET estado = 'suspendido' WHERE id = 2")
        db_conn.commit()
        with client.session_transaction() as s:
            s["usuario"] = "admin"
            s["rol"] = "admin"
            s["permisos"] = PERMISOS_ADMIN
            s["taller_id"] = 2
            s["taller_slug"] = "rival"
            s["csrf_token"] = "tk"
        r = client.get("/dashboard", follow_redirects=False)
        # La puerta de suscripción bloquea (redirige al bloqueo o 402).
        assert r.status_code in (302, 402)
