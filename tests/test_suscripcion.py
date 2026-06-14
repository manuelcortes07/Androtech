"""Tests de la SUSCRIPCIÓN del SaaS (Fase 3b).

Cubre: registro self-service (/signup), la puerta de acceso por suscripción
(bloqueo sin pérdida de datos), los webhooks de suscripción (sincronización de
estado + idempotencia) y el aislamiento (un taller no ve la suscripción de
otro). Stripe está SIEMPRE mockeado — ningún test toca la red.

El flujo de suscripción es SEPARADO del de pago de reparaciones; estos tests
mockean `saas_billing`, no el `stripe` global del flujo de reparaciones.
"""

import json
import datetime

import pytest
from sqlalchemy import text

import saas_billing
from auth import PERMISOS_ADMIN


# ───────────────────────── helpers / fixtures ──────────────────────────────
@pytest.fixture
def saas_mock(monkeypatch):
    """Hace creer a la app que Stripe-SaaS está configurado y mockea sus
    llamadas (sin red). El webhook 'verifica' la firma parseando el JSON."""
    monkeypatch.setattr(saas_billing, "is_configured", lambda: True)
    monkeypatch.setattr(saas_billing, "crear_customer",
                        lambda email, nombre: {"id": "cus_TEST"})
    monkeypatch.setattr(
        saas_billing, "crear_checkout_suscripcion",
        lambda customer_id, taller_id, success_url, cancel_url:
            {"url": "https://stripe.test/checkout"})
    monkeypatch.setattr(saas_billing, "crear_portal",
                        lambda customer_id, return_url: {"url": "https://stripe.test/portal"})
    monkeypatch.setattr(saas_billing, "STRIPE_SAAS_WEBHOOK_SECRET", "whsec_dummy")
    monkeypatch.setattr(saas_billing, "construir_evento",
                        lambda payload, sig: json.loads(payload))
    return saas_billing


def _fecha(delta_dias):
    return (datetime.datetime.now() + datetime.timedelta(days=delta_dias)
            ).strftime("%Y-%m-%d %H:%M:%S")


def _crear_taller(db_conn, tid, estado, trial_fin=None, customer="cus_X"):
    """Crea (o recrea) un taller con su admin para los tests de puerta."""
    db_conn.execute("DELETE FROM usuarios WHERE taller_id = ?", (tid,))
    db_conn.execute("DELETE FROM talleres WHERE id = ?", (tid,))
    db_conn.execute(
        "INSERT INTO talleres (id, nombre, slug, email_contacto, fecha_alta, "
        "estado, plan, trial_fin, stripe_customer_id) "
        "VALUES (?, ?, ?, ?, '2026-01-01', ?, 'basico', ?, ?)",
        (tid, f"Taller {tid}", f"t{tid}", f"t{tid}@x.com", estado, trial_fin, customer),
    )
    from werkzeug.security import generate_password_hash
    db_conn.execute(
        'INSERT INTO usuarios (taller_id, usuario, "contraseña", rol) '
        'VALUES (?, ?, ?, \'admin\')',
        (tid, "admin", generate_password_hash("x")),
    )
    db_conn.commit()


def _login_como(client, tid, slug):
    with client.session_transaction() as sess:
        sess["usuario"] = "admin"
        sess["rol"] = "admin"
        sess["permisos"] = PERMISOS_ADMIN
        sess["taller_id"] = tid
        sess["taller_slug"] = slug
        sess["csrf_token"] = "test-csrf-token"


def _webhook(client, event):
    return client.post("/saas/webhook", data=json.dumps(event),
                       headers={"Stripe-Signature": "t=1,v1=x"},
                       content_type="application/json")


def _ev(eid, tipo, obj):
    return {"id": eid, "type": tipo, "data": {"object": obj}}


# ───────────────────────────── /signup ─────────────────────────────────────
class TestSignup:
    def test_crea_taller_admin_en_trial(self, client, db_conn, saas_mock):
        r = client.post("/signup", data={
            "nombre_taller": "Reparaciones Pérez", "email": "perez@taller.com",
            "usuario": "admin", "password": "secreto123"})
        assert r.status_code == 302
        assert r.headers["Location"] == "https://stripe.test/checkout"

        row = db_conn.execute(
            "SELECT id, estado, trial_fin, stripe_customer_id FROM talleres "
            "WHERE slug = ?", ("reparaciones-perez",)).fetchone()
        assert row is not None
        assert row["estado"] == "trial"
        assert row["trial_fin"]               # trial_fin fijado
        assert row["stripe_customer_id"] == "cus_TEST"

        admin = db_conn.execute(
            "SELECT usuario, rol FROM usuarios WHERE taller_id = ?",
            (row["id"],)).fetchone()
        assert admin["usuario"] == "admin" and admin["rol"] == "admin"

    def test_email_duplicado_rechazado(self, client, db_conn, saas_mock):
        client.post("/signup", data={"nombre_taller": "Uno", "email": "dup@x.com",
                                     "usuario": "admin", "password": "secreto123"})
        r = client.post("/signup", data={"nombre_taller": "Dos", "email": "dup@x.com",
                                         "usuario": "admin", "password": "secreto123"})
        assert r.status_code == 400
        n = db_conn.execute(
            "SELECT COUNT(*) FROM talleres WHERE lower(email_contacto) = ?",
            ("dup@x.com",)).fetchone()[0]
        assert n == 1

    def test_password_corta_rechazada(self, client, db_conn, saas_mock):
        r = client.post("/signup", data={"nombre_taller": "Corta", "email": "c@x.com",
                                         "usuario": "admin", "password": "123"})
        assert r.status_code == 400
        assert db_conn.execute("SELECT COUNT(*) FROM talleres WHERE slug = ?",
                               ("corta",)).fetchone()[0] == 0

    def test_rollback_si_stripe_checkout_falla(self, client, db_conn, monkeypatch,
                                               saas_mock):
        def _boom(*a, **k):
            raise RuntimeError("stripe down")
        monkeypatch.setattr(saas_billing, "crear_checkout_suscripcion", _boom)
        r = client.post("/signup", data={
            "nombre_taller": "Fantasma", "email": "ghost@x.com",
            "usuario": "admin", "password": "secreto123"})
        assert r.status_code == 502
        # Rollback: NO debe quedar ni el taller ni su admin.
        assert db_conn.execute("SELECT COUNT(*) FROM talleres WHERE slug = ?",
                               ("fantasma",)).fetchone()[0] == 0


# ───────────────────────── puerta de acceso ────────────────────────────────
class TestPuertaAcceso:
    @pytest.mark.parametrize("estado,trial,permitido", [
        ("activo", None, True),
        ("trial", None, True),                 # trial sin fecha → permitido
        ("trial", "_FUTURO_", True),
        ("trial", "_PASADO_", False),
        ("suspendido", None, False),
        ("cancelado", None, False),
    ])
    def test_acceso_segun_estado(self, client, db_conn, estado, trial, permitido):
        tf = {"_FUTURO_": _fecha(5), "_PASADO_": _fecha(-1)}.get(trial, trial)
        _crear_taller(db_conn, 2, estado, tf)
        _login_como(client, 2, "t2")
        r = client.get("/dashboard")
        if permitido:
            assert r.status_code == 200
        else:
            assert r.status_code == 302
            assert "bloqueado" in r.headers.get("Location", "")

    def test_portal_publico_de_taller_suspendido_sigue_visible(self, client, db_conn):
        _crear_taller(db_conn, 2, "suspendido")
        # Sin login (cliente final). El portal público debe responder 200.
        r = client.get("/t/t2/consulta")
        assert r.status_code == 200

    def test_bloqueo_no_borra_datos(self, client, db_conn):
        _crear_taller(db_conn, 2, "suspendido")
        # Sembrar un cliente del taller 2
        db_conn.execute("INSERT INTO clientes (nombre, taller_id) VALUES (?, 2)",
                        ("Cliente B",))
        db_conn.commit()
        _login_como(client, 2, "t2")
        r = client.get("/dashboard")
        assert r.status_code == 302  # bloqueado
        # Los datos siguen intactos
        assert db_conn.execute(
            "SELECT COUNT(*) FROM clientes WHERE taller_id = 2").fetchone()[0] == 1
        assert db_conn.execute(
            "SELECT COUNT(*) FROM usuarios WHERE taller_id = 2").fetchone()[0] == 1


# ───────────────────────────── webhooks ────────────────────────────────────
class TestWebhook:
    def _estado(self, db_conn, tid=2):
        return db_conn.execute(
            "SELECT estado, stripe_sub_id FROM talleres WHERE id = ?",
            (tid,)).fetchone()

    def test_checkout_completed_guarda_subscription(self, client, db_conn, saas_mock):
        _crear_taller(db_conn, 2, "trial", customer="cus_X")
        r = _webhook(client, _ev("e1", "checkout.session.completed",
                                 {"customer": "cus_X", "subscription": "sub_1",
                                  "metadata": {"taller_id": "2"}}))
        assert r.status_code == 200
        row = self._estado(db_conn)
        assert row["estado"] == "trial" and row["stripe_sub_id"] == "sub_1"

    def test_subscription_updated_sincroniza_activo(self, client, db_conn, saas_mock):
        _crear_taller(db_conn, 2, "trial", customer="cus_X")
        _webhook(client, _ev("e2", "customer.subscription.updated",
                             {"customer": "cus_X", "id": "sub_1", "status": "active"}))
        assert self._estado(db_conn)["estado"] == "activo"

    def test_payment_failed_suspende(self, client, db_conn, saas_mock):
        _crear_taller(db_conn, 2, "activo", customer="cus_X")
        _webhook(client, _ev("e3", "invoice.payment_failed", {"customer": "cus_X"}))
        assert self._estado(db_conn)["estado"] == "suspendido"

    def test_invoice_paid_reactiva_suspendido(self, client, db_conn, saas_mock):
        _crear_taller(db_conn, 2, "suspendido", customer="cus_X")
        _webhook(client, _ev("e4", "invoice.paid", {"customer": "cus_X"}))
        assert self._estado(db_conn)["estado"] == "activo"

    def test_subscription_deleted_cancela(self, client, db_conn, saas_mock):
        _crear_taller(db_conn, 2, "activo", customer="cus_X")
        _webhook(client, _ev("e5", "customer.subscription.deleted",
                             {"customer": "cus_X", "id": "sub_1", "status": "canceled"}))
        assert self._estado(db_conn)["estado"] == "cancelado"

    def test_idempotencia_no_repite_efectos(self, client, db_conn, saas_mock):
        _crear_taller(db_conn, 2, "activo", customer="cus_X")
        # 1) suspende, 2) reenvía el MISMO id de un evento que reactivaría:
        ev_reactiva = _ev("dup", "invoice.paid", {"customer": "cus_X"})
        _webhook(client, _ev("susp", "invoice.payment_failed", {"customer": "cus_X"}))
        r1 = _webhook(client, ev_reactiva)
        assert r1.get_json()["status"] == "ok"
        assert self._estado(db_conn)["estado"] == "activo"
        # Reenvío del mismo event_id 'dup' → duplicate, sin efectos nuevos.
        # Primero re-suspendemos con OTRO id y comprobamos que el replay de 'dup'
        # NO reactiva.
        _webhook(client, _ev("susp2", "invoice.payment_failed", {"customer": "cus_X"}))
        assert self._estado(db_conn)["estado"] == "suspendido"
        r2 = _webhook(client, ev_reactiva)  # mismo id 'dup'
        assert r2.get_json()["status"] == "duplicate"
        assert self._estado(db_conn)["estado"] == "suspendido"  # no reactivó
        assert db_conn.execute(
            "SELECT COUNT(*) FROM stripe_eventos WHERE event_id = ?",
            ("dup",)).fetchone()[0] == 1

    def test_sin_secret_configurado_400(self, client, db_conn, monkeypatch):
        monkeypatch.setattr(saas_billing, "STRIPE_SAAS_WEBHOOK_SECRET", "")
        r = _webhook(client, _ev("x", "invoice.paid", {"customer": "cus_X"}))
        assert r.status_code == 400


# ─────────────────────── aislamiento de suscripción ────────────────────────
class TestAislamientoSuscripcion:
    def test_un_taller_no_ve_la_suscripcion_de_otro(self, client, db_conn, logged_admin):
        # Taller 2 con un customer distinto y marcador único.
        _crear_taller(db_conn, 2, "activo", customer="cus_SECRETO_DE_B")
        # logged_admin está logueado como taller 1 (androtech, activo).
        r = client.get("/suscripcion")
        assert r.status_code == 200
        cuerpo = r.get_data(as_text=True)
        # No debe filtrarse el customer del taller 2.
        assert "cus_SECRETO_DE_B" not in cuerpo
