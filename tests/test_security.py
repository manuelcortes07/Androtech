"""Tests de endurecimiento (B2): cabeceras de seguridad y política de contraseñas."""


def test_cabeceras_de_seguridad_presentes(client):
    r = client.get("/login")
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert "Referrer-Policy" in r.headers
    assert "Permissions-Policy" in r.headers
    csp = r.headers.get("Content-Security-Policy", "")
    # CSP presente y con la allowlist real de CDNs + protección de clickjacking.
    assert "default-src 'self'" in csp
    assert "https://cdn.jsdelivr.net" in csp
    assert "frame-ancestors 'self'" in csp


def test_signup_password_sin_mayuscula_rechazada(client, db_conn):
    # Política reforzada (validar_contraseña): exige mayúscula/minúscula/dígito.
    r = client.post("/signup", data={
        "nombre_taller": "Sin Mayus", "email": "sm@x.com",
        "usuario": "admin", "password": "secreto123"})  # sin mayúscula
    assert r.status_code == 400
    assert db_conn.execute(
        "SELECT COUNT(*) FROM talleres WHERE slug = ?", ("sin-mayus",)
    ).fetchone()[0] == 0


def test_signup_password_fuerte_aceptada(client, db_conn, monkeypatch):
    import saas_billing
    monkeypatch.setattr(saas_billing, "is_configured", lambda: False)
    r = client.post("/signup", data={
        "nombre_taller": "Con Mayus", "email": "cm@x.com",
        "usuario": "admin", "password": "Secreto123"})
    assert r.status_code == 302  # alta OK → redirect
    assert db_conn.execute(
        "SELECT COUNT(*) FROM talleres WHERE slug = ?", ("con-mayus",)
    ).fetchone()[0] == 1
