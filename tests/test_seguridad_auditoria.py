"""REPRODUCTORES de la auditoría de seguridad (read-only, NO arreglos).

Cada test de aquí DEMUESTRA un hallazgo: PASA mientras el agujero existe.
Cuando se arregle el fallo, el reproductor correspondiente debería FALLAR
(se convierte en test de regresión). NO borrar sin arreglar antes el fallo.

Reutiliza las fixtures del JUEZ (`dos_talleres`, `admin_A`) importándolas.
"""

import pytest

# Reutilizamos las fixtures y marcadores del juez de aislamiento.
from tests.test_aislamiento import (  # noqa: F401
    RIVAL_DISPOSITIVO,
    admin_A,
    dos_talleres,
)


# ════════════════════════════════════════════════════════════════════════
# HALLAZGO H1 (🟠) — Roles GLOBALES editables por cualquier admin de taller:
# un admin del taller A reescribe el rol 'tecnico' GLOBAL → afecta a los
# técnicos de TODOS los talleres (incluido B). Rompe el aislamiento en la
# superficie de roles (que está fuera del scope por decisión de producto,
# pero las rutas /admin/roles/* permiten mutarlo).
# ════════════════════════════════════════════════════════════════════════
class TestH1RolesGlobalesCrossTenant:
    def _id_rol(self, db_conn, nombre):
        row = db_conn.execute(
            "SELECT id FROM roles WHERE nombre = ?", (nombre,)
        ).fetchone()
        return row["id"] if row else None

    def test_admin_A_reescribe_rol_tecnico_global(self, admin_A, db_conn):
        # Asegura que existe el rol global 'tecnico' (lo siembra init_permisos_db;
        # si el entorno de test no lo tiene, lo creamos para el reproductor).
        tid = self._id_rol(db_conn, "tecnico")
        if tid is None:
            db_conn.execute(
                "INSERT INTO roles (nombre, descripcion, es_sistema, color) "
                "VALUES ('tecnico', 'base', 1, '#2B8AC4')"
            )
            db_conn.execute(
                "INSERT INTO permisos_rol (rol_nombre, permiso) VALUES ('tecnico','reparaciones_ver')"
            )
            db_conn.commit()
            tid = self._id_rol(db_conn, "tecnico")

        # Snapshot del estado GLOBAL para restaurarlo (el cambio es global y, de
        # hecho, contaminaría otros tests: eso ES la prueba del fallo).
        original = [row["permiso"] for row in db_conn.execute(
            "SELECT permiso FROM permisos_rol WHERE rol_nombre = 'tecnico'"
        ).fetchall()]
        try:
            # Admin del taller A (1) reescribe el rol 'tecnico' GLOBAL con un
            # permiso peligroso (borrar usuarios). editar_rol NO tiene @csrf_protect.
            r = admin_A.post(
                f"/admin/roles/editar/{tid}",
                data={"descripcion": "secuestrado por A", "color": "#000000",
                      "permisos": ["usuarios_borrar", "reparaciones_borrar"]},
                follow_redirects=False,
            )
            assert r.status_code in (302, 303)

            # El cambio quedó en la tabla GLOBAL permisos_rol (no scoped por taller):
            perms = {row["permiso"] for row in db_conn.execute(
                "SELECT permiso FROM permisos_rol WHERE rol_nombre = 'tecnico'"
            ).fetchall()}
            # PRUEBA DEL FALLO: el admin del taller A acaba de conceder a TODOS los
            # técnicos (de cualquier taller, incluido B) el permiso de borrar usuarios.
            assert "usuarios_borrar" in perms, (
                "REPRO H1: si esto falla, el rol global ya está aislado/bloqueado "
                "(el fallo estaría arreglado)."
            )
        finally:
            # Restaurar el estado global para no contaminar el resto de la suite.
            db_conn.execute("DELETE FROM permisos_rol WHERE rol_nombre = 'tecnico'")
            for p in original:
                db_conn.execute(
                    "INSERT INTO permisos_rol (rol_nombre, permiso) VALUES ('tecnico', ?)",
                    (p,),
                )
            db_conn.commit()


# ════════════════════════════════════════════════════════════════════════
# HALLAZGO H2 (🟠) — CSRF ausente en POST que mutan estado:
# /reparaciones/<id>/marcar-pagado NO lleva @csrf_protect ni validación
# manual de token → un sitio malicioso puede forzar a un usuario logueado a
# marcar una reparación como pagada (CSRF).
# ════════════════════════════════════════════════════════════════════════
class TestH2CsrfAusenteMarcarPagado:
    def test_marcar_pagado_sin_csrf_token_funciona(self, admin_A, db_conn, dos_talleres):
        repA = dos_talleres["repA"]
        # POST SIN campo csrf_token. Una ruta protegida lo rechazaría; ésta no.
        r = admin_A.post(
            f"/reparaciones/{repA}/marcar-pagado",
            data={"metodo_pago": "Efectivo"},  # ← sin csrf_token a propósito
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        estado = db_conn.execute(
            "SELECT estado_pago FROM reparaciones WHERE id = ?", (repA,)
        ).fetchone()["estado_pago"]
        # PRUEBA DEL FALLO: se marcó como pagada SIN token CSRF.
        assert estado == "Pagado", (
            "REPRO H2: si esto falla, marcar-pagado ya exige CSRF (arreglado)."
        )

    def test_contraste_ruta_protegida_rechaza_sin_csrf(self, admin_A, db_conn, dos_talleres):
        # Contraste: una ruta CON @csrf_protect NO aplica el cambio sin token.
        # Demuestra que H2 (marcar-pagado) es una omisión real, no el patrón general.
        cliA = dos_talleres["cliA"]
        admin_A.post(
            f"/clientes/editar/{cliA}",
            data={"nombre": "Hackeado", "telefono": "1", "email": "h@x.com"},
            follow_redirects=False,
        )
        nombre = db_conn.execute(
            "SELECT nombre FROM clientes WHERE id = ?", (cliA,)
        ).fetchone()["nombre"]
        # La ruta protegida BLOQUEÓ el cambio (sigue 'Cliente Comun'), al contrario
        # que marcar-pagado, que SÍ se aplicó sin token.
        assert nombre == "Cliente Comun"


# ════════════════════════════════════════════════════════════════════════
# HALLAZGO H3 (🔴) — ARREGLADO. El portal /consulta localiza por CÓDIGO público
# no adivinable, no por el id secuencial. Estos tests son ahora de REGRESIÓN:
# (1) iterar ?id= ya NO expone datos de otro taller, (2) un código inexistente
# no muestra nada, (3) el código correcto SÍ muestra su reparación (flujo legítimo).
# ════════════════════════════════════════════════════════════════════════
class TestH3ConsultaPublicaCrossTaller:
    def test_consulta_por_id_ya_no_expone_otro_taller(self, client, dos_talleres):
        repB = dos_talleres["repB"]  # reparación del taller B (2)
        r = client.get(f"/consulta?id={repB}")  # público, sin sesión
        assert r.status_code == 200
        # REGRESIÓN H3: el id secuencial ya NO resuelve ni muestra nada.
        assert RIVAL_DISPOSITIVO.encode() not in r.data

    def test_codigo_inexistente_no_muestra_nada(self, client, dos_talleres):
        r = client.get("/consulta?codigo=NoExisteJamas123")
        assert r.status_code == 200
        assert RIVAL_DISPOSITIVO.encode() not in r.data

    def test_codigo_correcto_muestra_su_reparacion(self, client, dos_talleres, db_conn):
        repB = dos_talleres["repB"]
        # El cliente del taller B recibe su código en el enlace/QR.
        db_conn.execute(
            "UPDATE reparaciones SET codigo_publico = ? WHERE id = ?",
            ("CODB-XYZ-1", repB),
        )
        db_conn.commit()
        r = client.get("/consulta?codigo=CODB-XYZ-1")
        assert r.status_code == 200
        # Quien tiene el código SÍ ve SU reparación (flujo legítimo, no enumerable).
        assert RIVAL_DISPOSITIVO.encode() in r.data
