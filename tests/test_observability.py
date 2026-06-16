"""Tests de observabilidad (B4): /health con readiness de BD y página 404."""


def test_health_incluye_estado_de_bd(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"
    # La BD de tests está disponible → readiness "ok".
    assert data["database"] == "ok"
    assert "timestamp" in data


def test_404_devuelve_pagina_limpia(client):
    r = client.get("/ruta-que-no-existe-jamas")
    assert r.status_code == 404
    cuerpo = r.get_data(as_text=True)
    # Página de error renderizada, sin trazas de Python.
    assert "Traceback" not in cuerpo
