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

    def test_login_with_valid_credentials(self, client, seed_admin, db_conn):
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

        # Y la sesión debe estar marcada COMPLETA: usuario, rol y permisos
        # (ampliado en Fase 1.3: antes no se verificaban los permisos, y el
        # camino obtener_permisos_usuario() es parte de lo migrado a ORM).
        from auth import PERMISOS_ADMIN
        with client.session_transaction() as sess:
            assert sess.get("usuario") == "admin"
            assert sess.get("rol") == "admin"
            assert sess.get("permisos") == PERMISOS_ADMIN

        # La auditoría debe haber registrado el evento 'login' (efecto real
        # del flujo migrado, no solo el redirect).
        row = db_conn.execute(
            "SELECT usuario FROM audit_log WHERE event_type='login' "
            "AND usuario='admin' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None, "login no registró evento de auditoría"

    def test_login_tecnico_loads_permisos_from_db(self, client, seed_tecnico):
        """El login de un técnico carga sus permisos desde permisos_rol.

        A diferencia del admin (short-circuit en memoria), el técnico ejerce
        la consulta real a BD vía SQLAlchemy en obtener_permisos_usuario().
        Añadido en Fase 1.3.
        """
        from auth import PERMISOS_TECNICO
        r = client.post(
            "/login",
            data={
                "usuario": "tecni",
                "contraseña": "tecnico123",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        assert r.status_code == 302
        with client.session_transaction() as sess:
            assert sess.get("rol") == "tecnico"
            assert sorted(sess.get("permisos", [])) == sorted(PERMISOS_TECNICO)

    def test_login_with_invalid_credentials_is_rejected(self, client, seed_admin,
                                                        db_conn):
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

        # El intento fallido queda en auditoría (ampliado en Fase 1.3).
        row = db_conn.execute(
            "SELECT usuario FROM audit_log WHERE event_type='login_failed' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None, "login fallido no registró auditoría"


# ════════════════════════════════════════════════════════════════════
# 3. Dashboard
# ════════════════════════════════════════════════════════════════════
class TestDashboard:
    def test_dashboard_loads_for_authenticated_user(self, logged_admin):
        r = logged_admin.get("/dashboard")
        assert r.status_code == 200

    def test_dashboard_renders_real_data(self, logged_admin, seed_reparacion):
        """El dashboard muestra datos reales de BD, no solo carga (Fase 1.3).

        Con la reparación sembrada (iPhone 12, 120 €, cliente 'Cliente Test'),
        las últimas reparaciones y los KPIs deben reflejarla en el HTML.
        """
        r = logged_admin.get("/dashboard")
        assert r.status_code == 200
        html = r.data.decode("utf-8", errors="replace")
        assert "iPhone 12" in html, "últimas reparaciones no muestran la sembrada"
        assert "Cliente Test" in html, "nombre del cliente no aparece"
        assert "120" in html, "el precio/ingresos no aparece en los KPIs"

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
# 4b. Fotos y firma de reparación (añadidos en Fase 1.5 — huecos conocidos)
# ════════════════════════════════════════════════════════════════════
class TestFotosFirma:
    # PNG 1x1 transparente válido
    _PNG_1PX = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfa\xcf"
        b"\xf0\xbf\x1e\x00\x06\x83\x02\x7f\x94\xad\xd0\xeb\x00\x00\x00\x00IEND"
        b"\xaeB`\x82"
    )

    def test_subir_foto_persists_in_db(self, logged_admin, seed_reparacion,
                                       db_conn):
        """Subir una foto crea la fila en fotos_reparacion (Fase 1.5)."""
        data = {
            "fotos": (io.BytesIO(self._PNG_1PX), "prueba.png"),
            "csrf_token": "test-csrf-token",
        }
        r = logged_admin.post(
            f"/reparaciones/{seed_reparacion}/fotos",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)

        row = db_conn.execute(
            "SELECT filename, subido_por FROM fotos_reparacion "
            "WHERE reparacion_id=? ORDER BY id DESC LIMIT 1",
            (seed_reparacion,),
        ).fetchone()
        assert row is not None, "la foto no se registró en BD"
        assert row["filename"].endswith(".png")
        assert row["subido_por"] == "admin"

    def test_guardar_firma_persists(self, logged_admin, seed_reparacion,
                                    db_conn):
        """Guardar la firma actualiza reparaciones.firma (Fase 1.5)."""
        import base64
        firma_b64 = "data:image/png;base64," + base64.b64encode(
            self._PNG_1PX).decode()

        r = logged_admin.post(
            f"/reparaciones/{seed_reparacion}/firma",
            json={"firma": firma_b64},
            headers={"X-CSRFToken": "test-csrf-token"},
        )
        assert r.status_code == 200
        assert r.get_json().get("success") is True

        row = db_conn.execute(
            "SELECT firma FROM reparaciones WHERE id=?",
            (seed_reparacion,),
        ).fetchone()
        assert row["firma"], "la columna firma quedó vacía"
        assert row["firma"].startswith(f"firma_{seed_reparacion}_")


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

    def test_edit_cliente_persists(self, logged_admin, seed_cliente, db_conn):
        """Editar un cliente persiste los cambios en BD (añadido Fase 1.4)."""
        r = logged_admin.post(
            f"/clientes/editar/{seed_cliente}",
            data={
                "nombre": "Cliente Renombrado",
                "telefono": "611223344",
                "email": "nuevo@email.com",
                "direccion": "Calle Nueva 9",
                "csrf_token": "test-csrf-token",
            },
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)

        row = db_conn.execute(
            "SELECT nombre, telefono, email, direccion FROM clientes WHERE id=?",
            (seed_cliente,),
        ).fetchone()
        assert row["nombre"] == "Cliente Renombrado"
        assert row["telefono"] == "611223344"
        assert row["email"] == "nuevo@email.com"
        assert row["direccion"] == "Calle Nueva 9"

    def test_delete_cliente_removes_row(self, logged_admin, seed_cliente,
                                        db_conn):
        """Borrar un cliente elimina la fila (añadido Fase 1.4)."""
        r = logged_admin.get(f"/clientes/borrar/{seed_cliente}",
                             follow_redirects=False)
        assert r.status_code in (302, 303)

        row = db_conn.execute(
            "SELECT id FROM clientes WHERE id=?", (seed_cliente,)
        ).fetchone()
        assert row is None, "el cliente sigue en BD tras borrarlo"

    def test_export_clientes_csv_content(self, logged_admin, seed_cliente,
                                         seed_reparacion):
        """El CSV de clientes contiene datos reales, no solo responde 200
        (añadido Fase 1.4 — las exportaciones eran hueco conocido)."""
        r = logged_admin.get("/exportar/clientes.csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("Content-Type", "")

        body = r.data.decode("utf-8-sig", errors="replace")
        assert "Cliente Test" in body, "el cliente sembrado no está en el CSV"
        assert "test@cliente.com" in body
        # La reparación sembrada (120 €) debe reflejarse en el facturado
        assert "120,00" in body, "el total facturado no aparece formateado"
        assert "INFORME COMPLETO DE CLIENTES" in body


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

        # Y la auditoría debe registrar el pago (ampliado en Fase 1.8)
        audit = db_conn.execute(
            "SELECT evento_datos FROM audit_log "
            "WHERE event_type='pago_registrado' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert audit is not None, "webhook no registró auditoría de pago"
        assert str(seed_reparacion) in audit["evento_datos"]

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


# ════════════════════════════════════════════════════════════════════
# 11. Multi-tenancy: resolución del taller (Fase 2.2)
# ════════════════════════════════════════════════════════════════════
class TestTenancyResolucion:
    def test_taller_1_existe_tras_migracion(self, db_conn):
        """La migración (Fase 2.1) dejó el taller 1 'androtech' creado."""
        row = db_conn.execute(
            "SELECT slug, nombre FROM talleres WHERE id=1"
        ).fetchone()
        assert row is not None
        assert row["slug"] == "androtech"

    def test_consulta_canonica_con_slug(self, client, seed_reparacion):
        """La ruta canónica /t/{slug}/consulta?id=X resuelve el taller y muestra
        la reparación (es la que imprimen los nuevos QR)."""
        r = client.get(f"/t/androtech/consulta?id={seed_reparacion}")
        assert r.status_code == 200
        assert b"iPhone 12" in r.data

    def test_slug_desconocido_da_404(self, client):
        """Un slug de taller inexistente → 404 (no se filtra a ciegas)."""
        r = client.get("/t/noexiste/consulta?id=1")
        assert r.status_code == 404

    def test_consulta_legacy_sin_slug_sigue_viva(self, client, seed_reparacion):
        """La legacy /consulta?id=X (QR ya impresos) sigue funcionando:
        resuelve el taller desde el id de la reparación."""
        r = client.get(f"/consulta?id={seed_reparacion}")
        assert r.status_code == 200
        assert b"iPhone 12" in r.data

    def test_login_legacy_default_taller_1(self, client, seed_admin):
        """El login legacy /login (sin slug) entra en el taller 1 y liga la
        sesión a ese taller."""
        r = client.post(
            "/login",
            data={"usuario": "admin", "contraseña": "admin123",
                  "csrf_token": "test-csrf-token"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        with client.session_transaction() as sess:
            assert sess.get("taller_id") == 1
            assert sess.get("taller_slug") == "androtech"

    def test_login_por_slug_resuelve_taller(self, client, seed_admin):
        """El login canónico /t/{slug}/login resuelve el taller desde el slug."""
        r = client.post(
            "/t/androtech/login",
            data={"usuario": "admin", "contraseña": "admin123",
                  "csrf_token": "test-csrf-token"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        with client.session_transaction() as sess:
            assert sess.get("taller_id") == 1

    def test_health_no_necesita_taller(self, client):
        """Las rutas de plataforma (health) no requieren taller y responden 200."""
        r = client.get("/health")
        assert r.status_code == 200
