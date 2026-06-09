"""Smoke tests — la RED DE SEGURIDAD para la migración SaaS.

Filosofía: amplitud > profundidad. Cubrimos los 10 flujos que el usuario
pidió como happy path. Si esta red pita tras un cambio, sabemos que algo
esencial se ha roto.

Estructura: una clase por flujo. Cada test es independiente; los datos se
limpian entre tests via `_reset_data` autouse en conftest.
"""

import io
import json


def stripe_webhook_event(event_type: str = "checkout.session.completed",
                         **metadata):
    """Construye un payload de webhook Stripe simulado para tests."""
    md = {"reparacion_id": "1", "cliente_email": "test@cliente.com"}
    md.update(metadata)
    return {
        "id": "evt_test_dummy",
        "type": event_type,
        "data": {
            "object": {
                "id": "cs_test_dummy_123",
                "payment_status": "paid",
                "amount_total": 12000,
                "metadata": md,
            }
        },
    }


# ════════════════════════════════════════════════════════════════════
# 1. Health endpoint
# ════════════════════════════════════════════════════════════════════
class TestHealth:
    def test_health_returns_200_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200

        data = r.get_json()
        assert data is not None
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "mail_configured" in data
        assert "python" in data


# ════════════════════════════════════════════════════════════════════
# 2. Login
# ════════════════════════════════════════════════════════════════════
class TestLogin:
    def test_login_page_loads(self, client):
        r = client.get("/login")
        assert r.status_code == 200
        assert b"contrase" in r.data  # forma parcial para evitar ñ encoding

    def test_login_with_valid_credentials(self, client, seed_admin):
        r = client.post(
            "/login",
            data={
                "usuario": "admin",
                "contraseña": "admin123",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        # Debe redirigir al dashboard
        assert r.status_code == 302
        assert "/dashboard" in r.headers.get("Location", "")

        # Y la sesión debe estar marcada
        with client.session_transaction() as sess:
            assert sess.get("usuario") == "admin"
            assert sess.get("rol") == "admin"

    def test_login_with_invalid_credentials_is_rejected(self, client, seed_admin):
        r = client.post(
            "/login",
            data={
                "usuario": "admin",
                "contraseña": "WRONG",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        # No debe redirigir al dashboard
        assert "/dashboard" not in r.headers.get("Location", "")

        # Y la sesión NO debe quedar autenticada
        with client.session_transaction() as sess:
            assert sess.get("usuario") is None


# ════════════════════════════════════════════════════════════════════
# 3. Dashboard
# ════════════════════════════════════════════════════════════════════
class TestDashboard:
    def test_dashboard_loads_for_authenticated_user(self, logged_admin):
        r = logged_admin.get("/dashboard")
        assert r.status_code == 200

    def test_dashboard_redirects_anonymous_user_to_login(self, client):
        r = client.get("/dashboard", follow_redirects=False)
        assert r.status_code == 302
        assert "/login" in r.headers.get("Location", "")


# ════════════════════════════════════════════════════════════════════
# 4. CRUD de reparaciones (entidad central)
# ════════════════════════════════════════════════════════════════════
class TestReparaciones:
    def test_list_reparaciones_loads(self, logged_admin, seed_reparacion):
        r = logged_admin.get("/reparaciones")
        assert r.status_code == 200
        # La reparación sembrada debe aparecer
        assert b"iPhone 12" in r.data

    def test_create_reparacion_persists_in_db(self, logged_admin,
                                              seed_cliente, db_conn):
        # GET del formulario debe responder
        r_get = logged_admin.get("/reparaciones/nueva")
        assert r_get.status_code == 200

        # POST con datos válidos
        r_post = logged_admin.post(
            "/reparaciones/nueva",
            data={
                "cliente_id": str(seed_cliente),
                "dispositivo": "Samsung Galaxy S21",
                "descripcion": "No enciende",
                "estado": "Pendiente",
                "precio": "85.50",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        # Tras crear, redirige
        assert r_post.status_code in (302, 303)

        # Verificación en BD
        row = db_conn.execute(
            "SELECT dispositivo, descripcion, precio, estado FROM reparaciones "
            "WHERE cliente_id=? ORDER BY id DESC LIMIT 1",
            (seed_cliente,),
        ).fetchone()
        assert row is not None
        assert row["dispositivo"] == "Samsung Galaxy S21"
        assert row["descripcion"] == "No enciende"
        assert abs(row["precio"] - 85.50) < 0.01
        assert row["estado"] == "Pendiente"

    def test_change_reparacion_state(self, logged_admin, seed_reparacion,
                                     seed_cliente, db_conn):
        r = logged_admin.post(
            f"/reparaciones/editar/{seed_reparacion}",
            data={
                "cliente_id": str(seed_cliente),
                "dispositivo": "iPhone 12",
                "descripcion": "Pantalla rota",
                "estado": "En proceso",
                "precio": "120.0",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        # Debe terminar en éxito (302 a edición o listado)
        assert r.status_code in (200, 302, 303)

        # Verificación en BD: estado actualizado
        row = db_conn.execute(
            "SELECT estado FROM reparaciones WHERE id=?",
            (seed_reparacion,),
        ).fetchone()
        assert row["estado"] == "En proceso"

        # Verificación BD: historial registró el cambio (regression test
        # de un bug detectado durante la migración Fase 1.2 — un FK mal
        # declarado en RepairHistorial hacía que el INSERT fallara
        # silenciosamente sin que ningún test lo detectara).
        hist = db_conn.execute(
            "SELECT estado_anterior, estado_nuevo, usuario "
            "FROM reparaciones_historial WHERE reparacion_id=? "
            "ORDER BY id DESC LIMIT 1",
            (seed_reparacion,),
        ).fetchone()
        assert hist is not None, "historial.registrar_cambio_estado no insertó nada"
        assert hist["estado_anterior"] == "Pendiente"
        assert hist["estado_nuevo"] == "En proceso"


# ════════════════════════════════════════════════════════════════════
# 5. CRUD de clientes
# ════════════════════════════════════════════════════════════════════
class TestClientes:
    def test_list_clientes_loads(self, logged_admin, seed_cliente):
        r = logged_admin.get("/clientes")
        assert r.status_code == 200
        assert b"Cliente Test" in r.data

    def test_create_cliente_persists(self, logged_admin, db_conn):
        r = logged_admin.post(
            "/clientes/nuevo",
            data={
                "nombre": "Maria Lopez",
                "telefono": "699112233",
                "email": "maria@example.com",
                "direccion": "Av. Andalucia 5",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)

        row = db_conn.execute(
            "SELECT nombre, telefono, email FROM clientes "
            "WHERE email=?",
            ("maria@example.com",),
        ).fetchone()
        assert row is not None
        assert row["nombre"] == "Maria Lopez"
        assert row["telefono"] == "699112233"


# ════════════════════════════════════════════════════════════════════
# 6. Inventario de piezas
# ════════════════════════════════════════════════════════════════════
class TestInventario:
    def test_list_inventario_loads(self, logged_admin):
        r = logged_admin.get("/inventario")
        assert r.status_code == 200

    def test_create_pieza_persists(self, logged_admin, db_conn):
        r = logged_admin.post(
            "/inventario/nueva",
            data={
                "nombre": "Pantalla iPhone 12",
                "categoria": "Pantallas",
                "descripcion": "Pantalla OEM compatible",
                "cantidad": "10",
                "cantidad_minima": "3",
                "precio_coste": "45.0",
                "precio_venta": "89.99",
                "proveedor": "ProvTest",
                "ubicacion": "Cajon A1",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)

        row = db_conn.execute(
            "SELECT nombre, cantidad, precio_venta FROM inventario_piezas "
            "WHERE nombre=?",
            ("Pantalla iPhone 12",),
        ).fetchone()
        assert row is not None
        assert row["cantidad"] == 10
        assert abs(row["precio_venta"] - 89.99) < 0.01


# ════════════════════════════════════════════════════════════════════
# 7. PDF de una reparación
# ════════════════════════════════════════════════════════════════════
class TestPDF:
    def test_pdf_reparacion_returns_pdf(self, logged_admin, seed_reparacion):
        r = logged_admin.get(f"/reparaciones/pdf/{seed_reparacion}")
        assert r.status_code == 200
        content_type = r.headers.get("Content-Type", "")
        assert "application/pdf" in content_type
        # Un PDF arranca con %PDF-
        assert r.data[:5] == b"%PDF-"


# ════════════════════════════════════════════════════════════════════
# 8. Portal público
# ════════════════════════════════════════════════════════════════════
class TestPortalPublico:
    def test_consulta_page_loads(self, client):
        r = client.get("/consulta")
        assert r.status_code == 200

    def test_consulta_by_id_finds_reparacion(self, client, seed_reparacion):
        # La consulta soporta ?id=X via GET (usado por el QR)
        r = client.get(f"/consulta?id={seed_reparacion}")
        assert r.status_code == 200
        assert b"iPhone 12" in r.data

    def test_consulta_unknown_id_shows_not_found(self, client):
        r = client.get("/consulta?id=99999")
        assert r.status_code == 200
        # Debe mostrar un mensaje de no encontrada
        assert (b"no se encontr" in r.data.lower()
                or b"No se encontr" in r.data)

    def test_solicitar_reparacion_page_loads(self, client):
        r = client.get("/solicitar-reparacion")
        assert r.status_code == 200

    def test_submit_solicitud_persists(self, client, db_conn):
        r = client.post(
            "/solicitar-reparacion",
            data={
                "nombre": "Juan Perez",
                "telefono": "666777888",
                "email": "juan@example.com",
                "dispositivo": "Laptop",
                "marca": "HP",
                "modelo": "Pavilion 15",
                "descripcion": "No carga la bateria",
                "urgencia": "normal",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        # Debe redirigir o renderizar success
        assert r.status_code in (200, 302, 303)

        row = db_conn.execute(
            "SELECT nombre, dispositivo FROM solicitudes_reparacion "
            "WHERE email=?",
            ("juan@example.com",),
        ).fetchone()
        assert row is not None
        assert row["nombre"] == "Juan Perez"
        assert row["dispositivo"] == "Laptop"


# ════════════════════════════════════════════════════════════════════
# 9. Webhook de Stripe (con evento simulado)
# ════════════════════════════════════════════════════════════════════
class TestStripeWebhook:
    def test_webhook_processes_checkout_session_completed(
        self, client, seed_reparacion, db_conn, monkeypatch
    ):
        """El webhook marca la reparación como pagada cuando recibe un evento
        válido firmado por Stripe."""
        import app as app_module

        # El evento simulado apunta a la reparación sembrada
        event = stripe_webhook_event(reparacion_id=str(seed_reparacion))

        # Mock de construct_event: devuelve el evento parseado sin verificar
        # firma real (que vendría de Stripe). En producción la firma protege
        # contra eventos falsificados; en tests confiamos en el mock.
        if app_module.stripe and hasattr(app_module.stripe, "Webhook"):
            monkeypatch.setattr(
                app_module.stripe.Webhook,
                "construct_event",
                lambda payload, sig, secret: event,
            )

        r = client.post(
            "/stripe/webhook",
            data=json.dumps(event),
            headers={"Stripe-Signature": "t=0,v1=dummy"},
            content_type="application/json",
        )
        assert r.status_code == 200

        # La reparación debe estar marcada como Pagado
        row = db_conn.execute(
            "SELECT estado_pago, metodo_pago FROM reparaciones WHERE id=?",
            (seed_reparacion,),
        ).fetchone()
        assert row["estado_pago"] == "Pagado"
        assert "Stripe" in (row["metodo_pago"] or "")

    def test_webhook_rejects_request_without_signature(self, client):
        r = client.post(
            "/stripe/webhook",
            data="{}",
            content_type="application/json",
        )
        # Sin header de firma debe rechazar
        assert r.status_code == 400


# ════════════════════════════════════════════════════════════════════
# 10. Permisos: ruta protegida rechaza a usuario sin permiso
# ════════════════════════════════════════════════════════════════════
class TestPermisos:
    def test_tecnico_cannot_access_admin_usuarios(self, logged_tecnico):
        """El tecnico no tiene 'usuarios_ver' → debe ser redirigido."""
        r = logged_tecnico.get("/admin/usuarios", follow_redirects=False)
        assert r.status_code == 302
        # Redirige al dashboard (comportamiento de @permiso_requerido)
        assert "/dashboard" in r.headers.get("Location", "")

    def test_admin_can_access_admin_usuarios(self, logged_admin):
        """El admin sí tiene acceso a /admin/usuarios."""
        r = logged_admin.get("/admin/usuarios")
        assert r.status_code == 200

    def test_anonymous_user_cannot_access_protected_route(self, client):
        """Sin sesión, las rutas protegidas redirigen a /login."""
        r = client.get("/clientes", follow_redirects=False)
        assert r.status_code == 302
        assert "/login" in r.headers.get("Location", "")
