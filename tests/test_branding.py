"""Rebranding: el EMISOR de los documentos es el TALLER, nunca la plataforma.

Cubre el hallazgo nº1 de REVISION_ESTADO.md (branding hardcodeado en los PDF):
- `_emisor()` funde los datos del taller sobre defaults seguros (sin "AndroTech").
- `taller_branding()` está aislado por taller (JUEZ): A nunca ve los datos de B.
- el formulario /perfil/taller persiste los datos y se reflejan en la marca.
"""

from flask import g

from branding import taller_branding
from utils.pdf_generator import _emisor, EMISOR_DEFAULT


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
