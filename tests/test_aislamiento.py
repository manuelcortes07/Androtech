"""EL JUEZ — Test de aislamiento cruzado multi-taller (Fase 2.5).

Innegociable y permanente. Crea el taller A (1, 'androtech') y el taller B
(2, 'rival') con datos DELIBERADAMENTE CLÓNICOS (mismo nombre de cliente,
mismo email, mismo usuario 'admin') y datos de B marcados con etiquetas únicas
('RIVAL', 'SECRETO'). Logueado como admin del taller A, verifica que NUNCA se
filtra nada del taller B por ninguna superficie.

Si este test se pone rojo, hay una fuga de datos entre talleres. Es el criterio
de aceptación de toda la Fase 2.
"""

import json

import pytest

# Marcadores ÚNICOS del taller B: si aparecen logueado como A, hay fuga.
RIVAL_DISPOSITIVO = "PixelRIVAL"
RIVAL_DESC = "SECRETO_de_B"
RIVAL_PIEZA = "PiezaRIVAL"
RIVAL_SOLICITANTE = "SolicitanteRIVAL"


@pytest.fixture
def dos_talleres(db_conn):
    """Taller A (1) y B (2) con datos clónicos + marcadores únicos en B.

    Devuelve ids relevantes del taller B para los tests de IDOR.
    """
    from werkzeug.security import generate_password_hash

    # ── Taller A (id=1, ya existe por la migración) ──────────────────
    db_conn.execute(
        'INSERT INTO usuarios (usuario, "contraseña", rol, taller_id) VALUES (?, ?, ?, 1)',
        ("admin", generate_password_hash("passA"), "admin"),
    )
    db_conn.execute(
        "INSERT INTO clientes (nombre, email, telefono, taller_id) "
        "VALUES ('Cliente Comun', 'comun@x.com', '600', 1)"
    )
    cliA = db_conn.execute("SELECT id FROM clientes WHERE taller_id=1").fetchone()["id"]
    db_conn.execute(
        "INSERT INTO reparaciones (cliente_id, dispositivo, descripcion, estado, "
        "fecha_entrada, precio, estado_pago, taller_id) "
        "VALUES (?, 'iPhoneA', 'normal de A', 'Pendiente', '2026-01-01', 100.0, 'Pendiente', 1)",
        (cliA,),
    )
    repA = db_conn.execute("SELECT id FROM reparaciones WHERE taller_id=1").fetchone()["id"]
    db_conn.execute("INSERT INTO inventario_piezas (nombre, taller_id) VALUES ('PiezaA', 1)")

    # ── Taller B (id=2) ──────────────────────────────────────────────
    db_conn.execute(
        "INSERT INTO talleres (id, nombre, slug, email_contacto, fecha_alta, estado, plan) "
        "VALUES (2, 'Rival', 'rival', 'r@x.com', '2026', 'activo', 'basico')"
    )
    db_conn.execute(
        'INSERT INTO usuarios (usuario, "contraseña", rol, taller_id) VALUES (?, ?, ?, 2)',
        ("admin", generate_password_hash("passB"), "admin"),  # mismo nombre!
    )
    db_conn.execute(
        "INSERT INTO clientes (nombre, email, telefono, taller_id) "
        "VALUES ('Cliente Comun', 'comun@x.com', '600', 2)"  # clónico!
    )
    cliB = db_conn.execute("SELECT id FROM clientes WHERE taller_id=2").fetchone()["id"]
    db_conn.execute(
        "INSERT INTO reparaciones (cliente_id, dispositivo, descripcion, estado, "
        "fecha_entrada, precio, estado_pago, taller_id) "
        f"VALUES (?, '{RIVAL_DISPOSITIVO}', '{RIVAL_DESC}', 'Pendiente', '2026-02-01', 987654.0, 'Pendiente', 2)",
        (cliB,),
    )
    repB = db_conn.execute("SELECT id FROM reparaciones WHERE taller_id=2").fetchone()["id"]
    db_conn.execute(
        f"INSERT INTO inventario_piezas (nombre, cantidad, taller_id) VALUES ('{RIVAL_PIEZA}', 5, 2)"
    )
    db_conn.execute(
        "INSERT INTO solicitudes_reparacion (nombre, telefono, dispositivo, descripcion, "
        f"fecha_solicitud, taller_id) VALUES ('{RIVAL_SOLICITANTE}', '699', 'Tablet', 'algo', '2026', 2)"
    )
    db_conn.execute(
        "INSERT INTO reparaciones_historial (reparacion_id, estado_nuevo, fecha_cambio, usuario, taller_id) "
        "VALUES (?, 'Pendiente', '2026-02-01 10:00:00', 'admin', 2)",
        (repB,),
    )
    db_conn.commit()
    return {"cliB": cliB, "repB": repB, "cliA": cliA, "repA": repA}


@pytest.fixture
def admin_A(client, dos_talleres):
    """Cliente HTTP logueado como admin del taller A (1)."""
    from auth import PERMISOS_ADMIN
    with client.session_transaction() as sess:
        sess["usuario"] = "admin"
        sess["rol"] = "admin"
        sess["permisos"] = PERMISOS_ADMIN
        sess["taller_id"] = 1
        sess["taller_slug"] = "androtech"
        sess["csrf_token"] = "tk"
    return client


def _sin_marcadores_b(data: bytes):
    """True si NINGÚN marcador único del taller B aparece en la respuesta."""
    txt = data.decode("utf-8", errors="replace")
    return not any(m in txt for m in (
        RIVAL_DISPOSITIVO, RIVAL_DESC, RIVAL_PIEZA, RIVAL_SOLICITANTE, "987654"
    ))


# ════════════════════════════════════════════════════════════════════
# (a) admin@A NUNCA ve datos de B en ninguna superficie interna
# ════════════════════════════════════════════════════════════════════
class TestAdminNoVeOtroTaller:
    @pytest.mark.parametrize("ruta", [
        "/dashboard",
        "/reparaciones",
        "/clientes",
        "/inventario",
        "/admin/usuarios",
        "/admin/solicitudes",
        "/cliente/historial",
        "/exportar/reparaciones.csv",
        "/exportar/clientes.csv",
        "/export/reparaciones",
        # Nota: el término buscado se refleja en la página, así que NO se busca
        # el marcador exacto (p. ej. 'PixelRIVAL') para no auto-disparar el
        # detector. Se buscan prefijos/términos que harían aflorar el dato de B
        # si hubiera fuga, sin contener el marcador completo.
        "/buscar?q=Pixel",
        "/buscar?q=Comun",
        "/api/calendario/eventos",
        "/api/inventario/buscar?q=Pieza",
    ])
    def test_superficie_no_filtra_taller_b(self, admin_A, ruta):
        r = admin_A.get(ruta)
        assert r.status_code in (200, 302), f"{ruta} respondió {r.status_code}"
        assert _sin_marcadores_b(r.data), f"FUGA: datos del taller B en {ruta}"

    def test_pdf_de_reparacion_propia_funciona(self, admin_A, dos_talleres):
        r = admin_A.get(f"/reparaciones/pdf/{dos_talleres['repA']}")
        assert r.status_code == 200
        assert r.data[:5] == b"%PDF-"


# ════════════════════════════════════════════════════════════════════
# (c) IDOR: por URL directa al id de B, NUNCA datos de B
# ════════════════════════════════════════════════════════════════════
class TestIDOR:
    @pytest.mark.parametrize("plantilla", [
        "/reparaciones/editar/{id}",
        "/reparaciones/pdf/{id}",
        "/reparaciones/{id}/ticket",
        "/reparaciones/{id}/firma",
    ])
    def test_acceso_directo_a_reparacion_de_b(self, admin_A, dos_talleres, plantilla):
        ruta = plantilla.format(id=dos_talleres["repB"])
        r = admin_A.get(ruta, follow_redirects=False)
        # Nunca 200 con datos de B: aceptable 302 (redirect) o 404. Si 200,
        # el cuerpo no puede contener marcadores de B.
        assert r.status_code != 200 or _sin_marcadores_b(r.data), \
            f"IDOR: {ruta} expuso datos del taller B (status {r.status_code})"

    def test_borrar_reparacion_de_b_no_afecta(self, admin_A, dos_talleres, db_conn):
        admin_A.get(f"/reparaciones/borrar/{dos_talleres['repB']}",
                    follow_redirects=False)
        # La reparación de B sigue existiendo (el filtro impidió borrarla).
        row = db_conn.execute(
            "SELECT id FROM reparaciones WHERE id=?", (dos_talleres["repB"],)
        ).fetchone()
        assert row is not None, "IDOR: se borró una reparación de otro taller"


# ════════════════════════════════════════════════════════════════════
# (b) Portal público canónico de A no devuelve reparaciones de B
# ════════════════════════════════════════════════════════════════════
class TestPortalPublico:
    def test_consulta_canonica_a_no_ve_id_de_b(self, client, dos_talleres):
        # /t/androtech/consulta?id=<id_de_B> → el filtro (taller 1) lo oculta.
        r = client.get(f"/t/androtech/consulta?id={dos_talleres['repB']}")
        assert r.status_code == 200
        assert _sin_marcadores_b(r.data), "portal canónico de A mostró reparación de B"

    def test_mis_reparaciones_a_por_email_clonico(self, client, dos_talleres):
        # Email que existe en AMBOS talleres → en el portal de A solo las de A.
        r = client.post(
            "/t/androtech/mis-reparaciones",
            data={"email": "comun@x.com", "csrf_token": "tk"},
        )
        assert r.status_code == 200
        assert _sin_marcadores_b(r.data), "mis-reparaciones de A devolvió datos de B"


# ════════════════════════════════════════════════════════════════════
# (d) Webhook: un pago de A jamás toca una reparación de B
# ════════════════════════════════════════════════════════════════════
class TestWebhookAislamiento:
    def _evento(self, reparacion_id, taller_id):
        return {"id": "evt", "type": "checkout.session.completed", "data": {"object": {
            "id": "cs_x", "payment_status": "paid", "amount_total": 99900,
            "metadata": {"reparacion_id": str(reparacion_id),
                         "taller_id": str(taller_id), "cliente_email": "comun@x.com"}}}}

    def test_pago_cruzado_rechazado(self, client, dos_talleres, db_conn, monkeypatch):
        import app as app_module
        repB = dos_talleres["repB"]
        # metadata dice taller 1 pero la reparación es de taller 2
        ev = self._evento(repB, 1)
        if app_module.stripe and hasattr(app_module.stripe, "Webhook"):
            monkeypatch.setattr(app_module.stripe.Webhook, "construct_event",
                                lambda p, s, sec: ev)
        r = client.post("/stripe/webhook", data=json.dumps(ev),
                        headers={"Stripe-Signature": "t=0,v1=x"},
                        content_type="application/json")
        assert r.status_code == 400, "webhook con taller cruzado no fue rechazado"
        estado = db_conn.execute(
            "SELECT estado_pago FROM reparaciones WHERE id=?", (repB,)
        ).fetchone()["estado_pago"]
        assert estado == "Pendiente", "FUGA: pago de A marcó pagada una reparación de B"


# ════════════════════════════════════════════════════════════════════
# (Plataforma) sin_filtro_taller() ve ambos y queda auditado
# ════════════════════════════════════════════════════════════════════
class TestPlataformaEscape:
    def test_escape_ve_ambos_talleres(self, app, dos_talleres, db_conn):
        from flask import g
        from sqlalchemy import select

        from database import get_session
        from models import Reparacion
        from tenancy import sin_filtro_taller
        with app.test_request_context("/dashboard"):
            g.taller_id = 1
            with sin_filtro_taller("auditoría de plataforma"):
                with get_session() as s:
                    todas = s.scalars(select(Reparacion)).all()
        dispositivos = {r.dispositivo for r in todas}
        assert "iPhoneA" in dispositivos and RIVAL_DISPOSITIVO in dispositivos
        aud = db_conn.execute(
            "SELECT taller_id FROM audit_log WHERE event_type='sin_filtro_taller' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert aud is not None and aud["taller_id"] is None
