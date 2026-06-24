"""Rebranding: el EMISOR de los documentos es el TALLER, nunca la plataforma.

Cubre el hallazgo nº1 de REVISION_ESTADO.md (branding hardcodeado en los PDF):
- `_emisor()` funde los datos del taller sobre defaults seguros (sin "AndroTech").
- `taller_branding()` está aislado por taller (JUEZ): A nunca ve los datos de B.
- el formulario /perfil/taller persiste los datos y se reflejan en la marca.
"""

import io
import json

from flask import g

from branding import taller_branding, logo_url_absoluto
from utils.pdf_generator import _emisor, EMISOR_DEFAULT

_PNG = b"\x89PNG\r\n\x1a\n" + b"logo-bytes-reales" * 4


def _logo_file_de(db_conn, tid):
    row = db_conn.execute("SELECT config FROM talleres WHERE id = ?", (tid,)).fetchone()
    cfg = json.loads(row[0]) if row and row[0] else {}
    return cfg.get("logo_file")


# ───────────────────────── _emisor: funde sobre defaults ────────────────────
def test_emisor_usa_datos_del_taller():
    e = _emisor({"nombre": "Reparaciones Pérez", "direccion": "Sevilla",
                 "telefono": "+34911", "email": "t@x.es", "nif": "B999",
                 "iva_rate": 0.10})
    assert e["name"] == "Reparaciones Pérez"
    assert e["address"] == "Sevilla"
    assert e["nif"] == "B999"
    assert e["iva_rate"] == 0.10
    # Nunca la marca de la plataforma ni la vieja.
    assert "AndroTech" not in e.values()
    assert "Kintsu" not in e.values()


def test_emisor_degrada_sin_datos():
    e = _emisor(None)
    assert e["name"] == EMISOR_DEFAULT["name"] == "Taller"
    assert e["iva_rate"] == 0.21
    assert e["address"] == ""  # sin dato → vacío, no "Huelva"


# ───────────────────────── taller_branding: aislado (JUEZ) ──────────────────
def _crear_taller2(db_conn):
    db_conn.execute(
        "INSERT INTO talleres (id, nombre, slug, email_contacto, telefono, "
        "direccion, fecha_alta, estado, plan) VALUES "
        "(2, 'Taller Beta', 'beta', 'beta@x.com', '+34999', 'Madrid', "
        "'2026-01-01', 'activo', 'basico')")
    db_conn.commit()


def test_taller_branding_aislado_por_taller(app, db_conn):
    _crear_taller2(db_conn)
    with app.test_request_context():
        g.taller_id = 1
        a = taller_branding()           # taller activo = 1
        b = taller_branding(2)          # explícito = 2
    assert b["nombre"] == "Taller Beta"
    assert b["direccion"] == "Madrid"
    # El taller A NO lleva los datos de B (ni al revés).
    assert a["nombre"] != b["nombre"]
    assert a["direccion"] != "Madrid"


def test_branding_telefono_wa_solo_digitos(app, db_conn):
    _crear_taller2(db_conn)
    with app.test_request_context():
        g.taller_id = 1
        b = taller_branding(2)
    assert b["telefono_wa"] == "34999"  # sin '+' ni espacios, para wa.me


# ───────────────────────── /perfil/taller persiste + se refleja ─────────────
def test_perfil_taller_actualiza_y_se_refleja(logged_admin, app, db_conn):
    r = logged_admin.post("/perfil/taller", data={
        "nombre": "Mi Taller Real", "direccion": "Cádiz, España",
        "telefono": "+34 600 700 800", "nif": "B12345678",
        "iva": "10", "moneda": "EUR", "web": "mitaller.com",
        "csrf_token": "test-csrf-token",
    })
    assert r.status_code == 302
    fila = db_conn.execute(
        "SELECT nombre, direccion, nif FROM talleres WHERE id = 1").fetchone()
    assert fila[0] == "Mi Taller Real"
    assert fila[2] == "B12345678"
    # La marca (lo que ven documentos/escaparate) ya refleja los nuevos datos.
    with app.test_request_context():
        g.taller_id = 1
        m = taller_branding()
    assert m["nombre"] == "Mi Taller Real"
    assert m["iva_rate"] == 0.10
    assert m["web"] == "mitaller.com"


def test_perfil_taller_nombre_vacio_se_rechaza(logged_admin, db_conn):
    antes = db_conn.execute("SELECT nombre FROM talleres WHERE id = 1").fetchone()[0]
    logged_admin.post("/perfil/taller", data={
        "nombre": "  ", "csrf_token": "test-csrf-token"})
    despues = db_conn.execute("SELECT nombre FROM talleres WHERE id = 1").fetchone()[0]
    assert despues == antes  # no se machacó con vacío


# ───────────────────────── chrome renderizado (los dos planos) ──────────────
class TestChromeRenderizado:
    def test_login_es_plataforma_kintsu(self, client):
        body = client.get("/login").get_data(as_text=True)
        assert "Kintsu" in body
        assert "AndroTech" not in body

    def test_portal_muestra_logo_del_taller_dueno_juez(self, client, db_conn):
        # Taller 1 con su logo; taller 2 con OTRO logo + una reparación.
        db_conn.execute("UPDATE talleres SET config = ? WHERE id = 1",
                        (json.dumps({"logo_file": "logo_t1.png"}),))
        db_conn.execute(
            "INSERT INTO talleres (id, nombre, slug, fecha_alta, estado, plan, config) "
            "VALUES (2, 'Taller Beta', 'beta', '2026-01-01', 'activo', 'basico', ?)",
            (json.dumps({"logo_file": "logo_t2.png"}),))
        db_conn.execute("INSERT INTO clientes (id, nombre, taller_id) VALUES (50, 'C', 2)")
        db_conn.execute(
            "INSERT INTO reparaciones (cliente_id, dispositivo, estado, taller_id, "
            "codigo_publico) VALUES (50, 'X', 'Pendiente', 2, 'BETACODE99')")
        db_conn.commit()
        body = client.get("/consulta?codigo=BETACODE99").get_data(as_text=True)
        assert "logo_t2.png" in body       # el logo del taller DUEÑO (2)
        assert "logo_t1.png" not in body   # JUEZ: nunca el de otro taller

    def test_accent_valido_se_inyecta_en_el_portal(self, logged_admin, client, db_conn):
        logged_admin.post("/perfil/taller", data={
            "nombre": "T", "accent_color": "#ff0000", "iva": "21",
            "moneda": "EUR", "csrf_token": "test-csrf-token"})
        body = client.get("/").get_data(as_text=True)
        assert "--accent:#ff0000" in body

    def test_accent_invalido_no_se_guarda(self, logged_admin, db_conn):
        logged_admin.post("/perfil/taller", data={
            "nombre": "T", "accent_color": "red;}body{display:none",
            "iva": "21", "csrf_token": "test-csrf-token"})
        row = db_conn.execute("SELECT config FROM talleres WHERE id = 1").fetchone()
        cfg = json.loads(row[0]) if row and row[0] else {}
        assert "accent_color" not in cfg  # no se inyecta basura en el CSS

    def test_panel_no_usa_el_accent_del_taller(self, logged_admin, db_conn):
        # El acento del taller es para el CLIENTE; el panel sigue siendo Kintsu.
        logged_admin.post("/perfil/taller", data={
            "nombre": "T", "accent_color": "#ff0000", "iva": "21",
            "csrf_token": "test-csrf-token"})
        body = logged_admin.get("/dashboard").get_data(as_text=True)
        assert "--accent:#ff0000" not in body

    def test_admin_blueprint_rutas_cargan(self, logged_admin):
        # Guarda el blueprint admin (movido por transformación): las rutas no
        # cubiertas por otros tests deben responder sin 500 (NameError, etc.).
        assert logged_admin.get("/admin/usuarios").status_code == 200
        assert logged_admin.get("/admin/sistema").status_code == 200
        assert logged_admin.get("/admin/test-email").status_code == 200
        assert logged_admin.get("/admin/solicitudes").status_code == 200
        assert logged_admin.get("/admin/auditoria").status_code == 200
        # seed-demo sin clave → 403 (no 500).
        assert logged_admin.get("/admin/seed-demo").status_code == 403

    def test_ficha_muestra_codigo_y_enlace_publico(self, logged_admin, db_conn):
        # UX: el taller ve el código y el enlace público para dárselo al cliente.
        db_conn.execute("INSERT INTO clientes (id, nombre, taller_id) VALUES (80, 'C', 1)")
        db_conn.execute(
            "INSERT INTO reparaciones (id, cliente_id, dispositivo, estado, taller_id, "
            "codigo_publico) VALUES (80, 80, 'iPhone', 'Pendiente', 1, 'TRACKCODE80')")
        db_conn.commit()
        body = logged_admin.get("/reparaciones/editar/80").get_data(as_text=True)
        assert "TRACKCODE80" in body
        assert "consulta?codigo=TRACKCODE80" in body  # enlace público completo

    def test_ficha_de_otro_taller_404_no_expone_codigo(self, logged_admin, db_conn):
        # JUEZ: la ficha (y su código) de otro taller NO es accesible.
        db_conn.execute("INSERT INTO talleres (id, nombre, slug, fecha_alta, estado, plan) "
                        "VALUES (2, 'B', 'b', '2026-01-01', 'activo', 'basico')")
        db_conn.execute("INSERT INTO clientes (id, nombre, taller_id) VALUES (81, 'C', 2)")
        db_conn.execute(
            "INSERT INTO reparaciones (id, cliente_id, dispositivo, estado, taller_id, "
            "codigo_publico) VALUES (81, 81, 'X', 'Pendiente', 2, 'OTHERCODE81')")
        db_conn.commit()
        r = logged_admin.get("/reparaciones/editar/81")
        assert r.status_code == 404
        assert "OTHERCODE81" not in r.get_data(as_text=True)

    def test_consulta_tolera_espacios_en_codigo(self, client, db_conn):
        db_conn.execute("INSERT INTO clientes (id, nombre, taller_id) VALUES (90, 'C', 1)")
        db_conn.execute(
            "INSERT INTO reparaciones (id, cliente_id, dispositivo, estado, taller_id, "
            "codigo_publico) VALUES (90, 90, 'iPhone 90', 'Terminado', 1, 'ABC123XYZ')")
        db_conn.commit()
        # Código tecleado con espacios de más (alrededor y en medio).
        r = client.post("/consulta", data={"codigo": "  ABC1 23X YZ  ", "csrf_token": "tk"})
        assert r.status_code == 200
        assert "iPhone 90" in r.get_data(as_text=True)

    def test_consulta_codigo_invalido_mensaje_generico(self, client):
        r = client.post("/consulta", data={"codigo": "NOEXISTE999", "csrf_token": "tk"})
        assert r.status_code == 200
        assert "No se encontró" in r.get_data(as_text=True)

    def test_consulta_no_busca_por_id_secuencial(self, client, db_conn):
        # H3: jamás por id. Teclear el id NO debe encontrar la reparación.
        db_conn.execute("INSERT INTO clientes (id, nombre, taller_id) VALUES (91, 'C', 1)")
        db_conn.execute(
            "INSERT INTO reparaciones (id, cliente_id, dispositivo, estado, taller_id, "
            "codigo_publico) VALUES (91, 91, 'SecretDevice', 'Terminado', 1, 'REALCODE91')")
        db_conn.commit()
        r = client.post("/consulta", data={"codigo": "91", "csrf_token": "tk"})  # el id
        assert r.status_code == 200
        assert "SecretDevice" not in r.get_data(as_text=True)

    def test_mis_reparaciones_muestra_repas_de_email_valido(self, client, db_conn):
        # Reproducción del reporte: con un email que SÍ tiene reparaciones en el
        # taller, /mis-reparaciones debe listarlas (no es regresión del refactor).
        db_conn.execute(
            "INSERT INTO clientes (id, nombre, email, taller_id) "
            "VALUES (70, 'Cli Portal', 'dueno@x.com', 1)")
        db_conn.execute(
            "INSERT INTO reparaciones (cliente_id, dispositivo, estado, taller_id, "
            "codigo_publico) VALUES (70, 'iPhone 77', 'Terminado', 1, 'CODE77')")
        db_conn.commit()
        r = client.post("/mis-reparaciones",
                        data={"email": "dueno@x.com", "csrf_token": "tk"})
        assert r.status_code == 200
        assert "iPhone 77" in r.get_data(as_text=True)  # la reparación aparece

    def test_normaliza_demo_existente_sin_tocar_otros(self, db_conn):
        from migrations import normalizar_taller_demo
        # BD existente: el demo (id 1) sigue con la marca vieja.
        db_conn.execute("UPDATE talleres SET nombre='AndroTech', "
                        "direccion='Huelva, España', telefono='+34 633 234 395' WHERE id=1")
        # Otro taller que a propósito se llama así: NO debe tocarse (JUEZ).
        db_conn.execute(
            "INSERT INTO talleres (id, nombre, slug, direccion, fecha_alta, estado, plan) "
            "VALUES (2, 'AndroTech Real', 't2', 'Huelva centro', '2026-01-01', 'activo', 'basico')")
        db_conn.commit()

        normalizar_taller_demo()

        r1 = db_conn.execute("SELECT nombre, direccion FROM talleres WHERE id=1").fetchone()
        r2 = db_conn.execute("SELECT nombre, direccion FROM talleres WHERE id=2").fetchone()
        assert r1[0] != "AndroTech" and "Huelva" not in (r1[1] or "")  # demo normalizado
        assert r2[0] == "AndroTech Real" and r2[1] == "Huelva centro"   # otro taller INTACTO

        # Idempotente: una 2ª pasada no vuelve a cambiar nada.
        antes = db_conn.execute("SELECT nombre FROM talleres WHERE id=1").fetchone()[0]
        normalizar_taller_demo()
        assert db_conn.execute("SELECT nombre FROM talleres WHERE id=1").fetchone()[0] == antes

    def test_escaparate_lleva_el_nombre_del_taller(self, client, db_conn):
        # Renombra el taller 1 y comprueba que el escaparate lo muestra (no la marca).
        db_conn.execute("UPDATE talleres SET nombre = 'Reparaciones Pérez' WHERE id = 1")
        db_conn.commit()
        body = client.get("/").get_data(as_text=True)
        assert "Reparaciones Pérez" in body
        assert "AndroTech" not in body
        # La plataforma sólo aparece como crédito discreto "Hecho con Kintsu",
        # nunca como marca principal del escaparate.
        assert body.count("Kintsu") <= 2  # comentario CSS + "Hecho con Kintsu"
        assert "Hecho con Kintsu" in body


# ───────────────────────── uploader de logo (/perfil) ──────────────────────
class TestUploaderLogo:
    def test_subir_logo_valido_guarda_config(self, logged_admin, db_conn):
        data = {"logo": (io.BytesIO(_PNG), "milogo.png"),
                "csrf_token": "test-csrf-token"}
        r = logged_admin.post("/perfil/logo", data=data,
                              content_type="multipart/form-data")
        assert r.status_code == 302
        f = _logo_file_de(db_conn, 1)
        assert f and f.startswith("logo_1_") and f.endswith(".png")

    def test_logo_trucado_se_rechaza(self, logged_admin, db_conn):
        # Extensión de imagen pero contenido NO imagen (magic bytes falsos).
        data = {"logo": (io.BytesIO(b"esto no es una imagen"), "fake.png"),
                "csrf_token": "test-csrf-token"}
        logged_admin.post("/perfil/logo", data=data,
                          content_type="multipart/form-data")
        assert _logo_file_de(db_conn, 1) is None  # no se guardó

    def test_quitar_logo(self, logged_admin, db_conn):
        logged_admin.post("/perfil/logo",
                          data={"logo": (io.BytesIO(_PNG), "l.png"),
                                "csrf_token": "test-csrf-token"},
                          content_type="multipart/form-data")
        assert _logo_file_de(db_conn, 1) is not None
        r = logged_admin.post("/perfil/logo/eliminar",
                              data={"csrf_token": "test-csrf-token"})
        assert r.status_code == 302
        assert _logo_file_de(db_conn, 1) is None

    def test_juez_logo_no_cruza_de_taller(self, logged_admin, db_conn):
        # El admin del taller 1 sube su logo; el taller 2 NO debe verse afectado.
        _crear_taller2(db_conn)
        logged_admin.post("/perfil/logo",
                          data={"logo": (io.BytesIO(_PNG), "l.png"),
                                "csrf_token": "test-csrf-token"},
                          content_type="multipart/form-data")
        assert _logo_file_de(db_conn, 1) is not None
        assert _logo_file_de(db_conn, 2) is None  # taller 2 intacto

    def test_email_al_cliente_incluye_logo_absoluto(self, app, db_conn, monkeypatch):
        import app as A
        db_conn.execute("UPDATE talleres SET config = ? WHERE id = 1",
                        (json.dumps({"logo_file": "logo_e.png"}),))
        db_conn.commit()
        capt = {}
        monkeypatch.setattr(A.email_service, "_send", lambda **k: capt.update(k))
        with app.test_request_context("http://taller.example/x"):
            g.taller_id = 1
            A.email_service.send_repair_status_update(
                "c@x.com", "Cli", 1, "Pendiente", "Terminado", "iPhone", "desc")
        assert "http://taller.example/static/uploads/logos/logo_e.png" in capt["html_body"]

    def test_email_sin_logo_degrada_a_nombre(self, app, db_conn, monkeypatch):
        import app as A
        db_conn.execute("UPDATE talleres SET nombre = 'Taller Zeta', config = NULL WHERE id = 1")
        db_conn.commit()
        capt = {}
        monkeypatch.setattr(A.email_service, "_send", lambda **k: capt.update(k))
        with app.test_request_context("http://taller.example/x"):
            g.taller_id = 1
            A.email_service.send_repair_status_update(
                "c@x.com", "Cli", 1, "Pendiente", "Terminado", "iPhone", "desc")
        assert "Taller Zeta" in capt["html_body"]
        assert "uploads/logos" not in capt["html_body"]

    def test_branding_resuelve_rutas_del_logo(self, logged_admin, app, db_conn):
        logged_admin.post("/perfil/logo",
                          data={"logo": (io.BytesIO(_PNG), "l.png"),
                                "csrf_token": "test-csrf-token"},
                          content_type="multipart/form-data")
        with app.test_request_context():
            g.taller_id = 1
            m = taller_branding()
        assert m["logo_static"].startswith("uploads/logos/logo_1_")
        assert m["logo_path"].endswith(m["logo_file"])  # ruta de fichero (PDF)
        # URL absoluta para emails (con base) vs degradación sin base.
        assert logo_url_absoluto(m, base_url="https://kintsu.app").startswith(
            "https://kintsu.app/static/uploads/logos/")
        assert logo_url_absoluto({"logo_static": ""}, base_url="https://x") == ""
