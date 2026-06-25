"""REPRODUCTORES de la auditoría de seguridad (read-only, NO arreglos).

Cada test de aquí DEMUESTRA un hallazgo: PASA mientras el agujero existe.
Cuando se arregle el fallo, el reproductor correspondiente debería FALLAR
(se convierte en test de regresión). NO borrar sin arreglar antes el fallo.

Reutiliza las fixtures del JUEZ (`dos_talleres`, `admin_A`) importándolas.
"""

import json

import pytest

# Reutilizamos las fixtures y marcadores del juez de aislamiento.
from tests.test_aislamiento import (  # noqa: F401
    RIVAL_DISPOSITIVO,
    admin_A,
    dos_talleres,
)
from tests.test_smoke import stripe_webhook_event


def _mock_construct(monkeypatch, event):
    import app as app_module
    if app_module.stripe and hasattr(app_module.stripe, "Webhook"):
        monkeypatch.setattr(app_module.stripe.Webhook, "construct_event",
                            lambda payload, sig, secret: event)


# ════════════════════════════════════════════════════════════════════════
# HALLAZGO H4/H6 (🟠) — ARREGLADO. Webhook de reparaciones: firma obligatoria
# (falla cerrado), idempotente y rechaza importes que no cuadran.
# ════════════════════════════════════════════════════════════════════════
class TestH4H6WebhookReparaciones:
    def test_h4_sin_libreria_stripe_falla_cerrado(self, client, seed_reparacion, db_conn, monkeypatch):
        # El webhook vive ahora en blueprints/pagos.py (refactor B1): se parchea
        # ahí el nombre `stripe` que lee la ruta.
        import blueprints.pagos as pagos_module
        monkeypatch.setattr(pagos_module, "stripe", None)  # no se puede verificar firma
        ev = stripe_webhook_event(reparacion_id=str(seed_reparacion))
        r = client.post("/stripe/webhook", data=json.dumps(ev),
                        headers={"Stripe-Signature": "t=0,v1=x"},
                        content_type="application/json")
        # REGRESIÓN H4: antes parseaba sin verificar y marcaba pagado; ahora 503.
        assert r.status_code == 503
        estado = db_conn.execute(
            "SELECT estado_pago FROM reparaciones WHERE id=?", (seed_reparacion,)
        ).fetchone()["estado_pago"]
        assert estado != "Pagado"

    def test_h6_importe_no_coincide_no_paga(self, client, seed_reparacion, db_conn, monkeypatch):
        ev = stripe_webhook_event(reparacion_id=str(seed_reparacion))
        ev["data"]["object"]["amount_total"] = 999  # 9,99 € != 120,00 €
        _mock_construct(monkeypatch, ev)
        r = client.post("/stripe/webhook", data=json.dumps(ev),
                        headers={"Stripe-Signature": "x"},
                        content_type="application/json")
        # REGRESIÓN H6: importe discrepante → rechazado, NO pagado.
        assert r.status_code == 400
        estado = db_conn.execute(
            "SELECT estado_pago FROM reparaciones WHERE id=?", (seed_reparacion,)
        ).fetchone()["estado_pago"]
        assert estado != "Pagado"
        # y queda constancia en audit_log
        n = db_conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE event_type='pago_importe_no_coincide'"
        ).fetchone()[0]
        assert n >= 1

    def test_h6_evento_repetido_es_idempotente(self, client, seed_reparacion, db_conn, monkeypatch):
        ev = stripe_webhook_event(reparacion_id=str(seed_reparacion))  # id evt_test_dummy
        _mock_construct(monkeypatch, ev)

        def _post():
            return client.post("/stripe/webhook", data=json.dumps(ev),
                               headers={"Stripe-Signature": "x"},
                               content_type="application/json")

        r1 = _post()
        r2 = _post()
        assert r1.status_code == 200
        assert r2.status_code == 200
        # REGRESIÓN H6: la 2ª entrega es idempotente (no reprocesa).
        assert json.loads(r2.data).get("status") == "duplicate"
        # la auditoría de pago se registró UNA sola vez.
        n = db_conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE event_type='pago_registrado'"
        ).fetchone()[0]
        assert n == 1


# ════════════════════════════════════════════════════════════════════════
# HALLAZGO H1 (🟠) — ARREGLADO. Los roles siguen GLOBALES pero su edición queda
# reservada al SUPERADMIN DE PLATAFORMA. Tests de REGRESIÓN:
# (1) un admin de taller normal recibe 403 al intentar editar un rol global,
#     y el rol NO cambia; (2) el superadmin SÍ puede.
# ════════════════════════════════════════════════════════════════════════
class TestH1RolesGlobalesCrossTenant:
    def _id_rol(self, db_conn, nombre):
        row = db_conn.execute(
            "SELECT id FROM roles WHERE nombre = ?", (nombre,)
        ).fetchone()
        return row["id"] if row else None

    def _asegura_tecnico(self, db_conn):
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
        return tid

    def test_admin_taller_no_puede_editar_rol_global(self, admin_A, db_conn):
        # admin_A está logueado como admin del taller A SIN es_superadmin.
        tid = self._asegura_tecnico(db_conn)
        original = {row["permiso"] for row in db_conn.execute(
            "SELECT permiso FROM permisos_rol WHERE rol_nombre = 'tecnico'"
        ).fetchall()}

        r = admin_A.post(
            f"/admin/roles/editar/{tid}",
            data={"descripcion": "secuestrado", "color": "#000000",
                  "permisos": ["usuarios_borrar", "reparaciones_borrar"]},
            follow_redirects=False,
        )
        # REGRESIÓN H1: un admin de taller normal NO puede tocar roles globales.
        assert r.status_code == 403
        # y el rol global quedó intacto.
        despues = {row["permiso"] for row in db_conn.execute(
            "SELECT permiso FROM permisos_rol WHERE rol_nombre = 'tecnico'"
        ).fetchall()}
        assert despues == original

    def test_superadmin_si_puede_editar_rol_global(self, client, dos_talleres, db_conn):
        from auth import PERMISOS_ADMIN
        tid = self._asegura_tecnico(db_conn)
        original = [row["permiso"] for row in db_conn.execute(
            "SELECT permiso FROM permisos_rol WHERE rol_nombre = 'tecnico'"
        ).fetchall()]
        try:
            with client.session_transaction() as s:
                s["usuario"] = "admin"
                s["rol"] = "admin"
                s["permisos"] = PERMISOS_ADMIN
                s["taller_id"] = 1
                s["taller_slug"] = "androtech"
                s["csrf_token"] = "tk"
                s["es_superadmin"] = True  # designado por la plataforma
            r = client.post(
                f"/admin/roles/editar/{tid}",
                data={"descripcion": "ok", "color": "#222222",
                      "permisos": ["reparaciones_ver", "clientes_ver"]},
                follow_redirects=False,
            )
            assert r.status_code in (302, 303)
            perms = {row["permiso"] for row in db_conn.execute(
                "SELECT permiso FROM permisos_rol WHERE rol_nombre = 'tecnico'"
            ).fetchall()}
            assert perms == {"reparaciones_ver", "clientes_ver"}
        finally:
            db_conn.execute("DELETE FROM permisos_rol WHERE rol_nombre = 'tecnico'")
            for p in original:
                db_conn.execute(
                    "INSERT INTO permisos_rol (rol_nombre, permiso) VALUES ('tecnico', ?)",
                    (p,),
                )
            db_conn.commit()


# ════════════════════════════════════════════════════════════════════════
# HALLAZGO H2 (🟠) — ARREGLADO. CSRF POR DEFECTO en todo POST (salvo webhooks).
# Tests de REGRESIÓN. La autouse `_disable_csrf_validation` desactiva el CSRF en
# los tests; aquí lo REACTIVAMOS (validación real) para demostrar el bloqueo.
# ════════════════════════════════════════════════════════════════════════
def _reactivar_csrf_real(monkeypatch):
    """Restaura una validación CSRF REAL (la autouse la deja en True)."""
    import hmac

    from flask import request, session

    import app as app_mod
    import utils.security as security_mod

    def _real():
        sent = (request.form.get("csrf_token", "")
                or request.headers.get("X-CSRFToken", ""))
        expected = session.get("csrf_token", "")
        return bool(sent) and bool(expected) and hmac.compare_digest(str(sent), str(expected))

    monkeypatch.setattr(security_mod, "validate_csrf", _real)
    monkeypatch.setattr(app_mod, "validate_csrf", _real)


class TestH2CsrfPorDefecto:
    def test_marcar_pagado_sin_csrf_es_rechazado(self, admin_A, db_conn, dos_talleres, monkeypatch):
        _reactivar_csrf_real(monkeypatch)
        repA = dos_talleres["repA"]
        admin_A.post(
            f"/reparaciones/{repA}/marcar-pagado",
            data={"metodo_pago": "Efectivo"},  # ← sin csrf_token
            follow_redirects=False,
        )
        # REGRESIÓN H2: rechazado (redirect sin aplicar), NO marcado como pagado.
        estado = db_conn.execute(
            "SELECT estado_pago FROM reparaciones WHERE id = ?", (repA,)
        ).fetchone()["estado_pago"]
        assert estado != "Pagado"

    def test_marcar_pagado_con_csrf_funciona(self, admin_A, db_conn, dos_talleres, monkeypatch):
        _reactivar_csrf_real(monkeypatch)
        repA = dos_talleres["repA"]
        # admin_A tiene session['csrf_token'] = 'tk'; enviamos el token correcto.
        r = admin_A.post(
            f"/reparaciones/{repA}/marcar-pagado",
            data={"metodo_pago": "Efectivo", "csrf_token": "tk"},
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)
        estado = db_conn.execute(
            "SELECT estado_pago FROM reparaciones WHERE id = ?", (repA,)
        ).fetchone()["estado_pago"]
        assert estado == "Pagado"

    def test_post_sin_token_en_ruta_cualquiera_rechazado(self, admin_A, db_conn, dos_talleres, monkeypatch):
        # CSRF por defecto: incluso una ruta que antes dependía sólo del decorador
        # queda protegida. Subir/editar sin token → rechazado.
        _reactivar_csrf_real(monkeypatch)
        cliA = dos_talleres["cliA"]
        admin_A.post(
            f"/clientes/editar/{cliA}",
            data={"nombre": "Hackeado", "telefono": "1", "email": "h@x.com"},
            follow_redirects=False,
        )
        nombre = db_conn.execute(
            "SELECT nombre FROM clientes WHERE id = ?", (cliA,)
        ).fetchone()["nombre"]
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


# ════════════════════════════════════════════════════════════════════════
# HALLAZGO H5 (🟡) — ARREGLADO. mis_reparaciones: rate-limit + anti-enumeración.
# ════════════════════════════════════════════════════════════════════════
class TestH5MisReparaciones:
    def test_anti_enumeracion_mismo_mensaje(self, client, seed_cliente):
        # Email de un cliente REAL sin reparaciones vs email inexistente:
        # misma salida genérica (no revela si el email es cliente).
        r1 = client.post("/mis-reparaciones",
                         data={"email": "test@cliente.com", "csrf_token": "x"})
        r2 = client.post("/mis-reparaciones",
                         data={"email": "nadie@ninguno.com", "csrf_token": "x"})
        assert b"No encontramos reparaciones" in r1.data
        assert b"No encontramos reparaciones" in r2.data
        # el nombre del cliente real NO aparece (no se filtra su existencia)
        assert b"Cliente Test" not in r1.data

    def test_rate_limit_dispara(self, client, monkeypatch):
        import app as app_module
        monkeypatch.setattr(app_module.limiter, "enabled", True)
        try:
            app_module.limiter.reset()
        except Exception:
            pass
        last = None
        for i in range(32):  # límite 30/min
            last = client.post("/mis-reparaciones",
                               data={"email": f"x{i}@y.com", "csrf_token": "x"},
                               follow_redirects=False)
        # Superado el límite: el handler 429 redirige (302) — o 429 directo.
        assert last.status_code in (302, 429)


# ════════════════════════════════════════════════════════════════════════
# HALLAZGO H7 (🟡) — ARREGLADO. Login regenera la sesión (anti-fixation).
# ════════════════════════════════════════════════════════════════════════
class TestH7SesionRegenerada:
    def test_login_descarta_sesion_previa(self, client, seed_admin):
        with client.session_transaction() as s:
            s["fijado_por_atacante"] = "valor-malicioso"
        client.post("/login", data={"usuario": "admin", "contraseña": "admin123",
                                    "csrf_token": "x"}, follow_redirects=False)
        with client.session_transaction() as s:
            assert "fijado_por_atacante" not in s   # sesión regenerada
            assert s.get("usuario") == "admin"      # login OK
            assert s.get("permisos")                # permisos frescos cargados


# ════════════════════════════════════════════════════════════════════════
# HALLAZGO H8 (🟡) — ARREGLADO. Los errores no vuelcan str(excepción) a la UI.
# ════════════════════════════════════════════════════════════════════════
class TestH8NoFiltraExcepciones:
    def test_excepcion_no_aparece_en_respuesta(self, client, seed_reparacion, monkeypatch):
        # publico_pagar vive ahora en blueprints/pagos.py (refactor B1): se
        # parchea ahí el get_session que usa la ruta.
        import blueprints.pagos as pagos_module
        SECRET = "TRAZA_INTERNA_SECRETA_9988"

        def _boom(*a, **k):
            raise RuntimeError(SECRET)

        monkeypatch.setattr(pagos_module, "get_session", _boom)
        r = client.post(f"/publico/pagar/{seed_reparacion}",
                        data={"cliente_email": "a@b.com", "csrf_token": "x"},
                        follow_redirects=True)
        assert SECRET.encode() not in r.data           # no se filtra la traza
        assert b"No se pudo completar" in r.data        # mensaje genérico


# ════════════════════════════════════════════════════════════════════════
# HALLAZGO H9 (🟡) — ARREGLADO. Backend del limiter configurable (Redis en prod).
# ════════════════════════════════════════════════════════════════════════
class TestH9LimiterStorage:
    def test_default_memory(self):
        import app as app_module
        assert app_module._RATELIMIT_STORAGE == "memory://"

    def test_env_configura_backend(self, monkeypatch):
        import app as app_module
        monkeypatch.setenv("RATELIMIT_STORAGE_URI", "redis://cache:6379/0")
        assert app_module._resolve_ratelimit_storage() == "redis://cache:6379/0"
        monkeypatch.delenv("RATELIMIT_STORAGE_URI")
        monkeypatch.setenv("REDIS_URL", "redis://otro:6379")
        assert app_module._resolve_ratelimit_storage() == "redis://otro:6379"


# ════════════════════════════════════════════════════════════════════════
# HALLAZGO H10 (🟡) — ARREGLADO. Subidas: magic bytes + límite por archivo.
# ════════════════════════════════════════════════════════════════════════
class TestH10Uploads:
    def _png(self, n=64):
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * n

    def test_archivo_trucado_rechazado(self, logged_admin, db_conn):
        import io

        from tests.test_quality import _seed_reparacion
        rid = _seed_reparacion(db_conn, 1)
        data = {"fotos": (io.BytesIO(b"esto no es una imagen"), "evil.png")}
        logged_admin.post(f"/reparaciones/{rid}/fotos", data=data,
                          content_type="multipart/form-data")
        n = db_conn.execute(
            "SELECT COUNT(*) FROM fotos_reparacion WHERE reparacion_id=?", (rid,)
        ).fetchone()[0]
        assert n == 0  # extensión .png pero contenido NO imagen → rechazado

    def test_imagen_valida_aceptada(self, logged_admin, db_conn):
        import io

        from tests.test_quality import _seed_reparacion
        rid = _seed_reparacion(db_conn, 1)
        data = {"fotos": (io.BytesIO(self._png()), "ok.png")}
        logged_admin.post(f"/reparaciones/{rid}/fotos", data=data,
                          content_type="multipart/form-data")
        n = db_conn.execute(
            "SELECT COUNT(*) FROM fotos_reparacion WHERE reparacion_id=?", (rid,)
        ).fetchone()[0]
        assert n == 1  # PNG real → aceptado

    def test_supera_5mb_rechazado(self, logged_admin, db_conn):
        import io

        from tests.test_quality import _seed_reparacion
        rid = _seed_reparacion(db_conn, 1)
        big = self._png(5 * 1024 * 1024 + 1)  # PNG válido pero > 5 MB
        data = {"fotos": (io.BytesIO(big), "big.png")}
        logged_admin.post(f"/reparaciones/{rid}/fotos", data=data,
                          content_type="multipart/form-data")
        n = db_conn.execute(
            "SELECT COUNT(*) FROM fotos_reparacion WHERE reparacion_id=?", (rid,)
        ).fetchone()[0]
        assert n == 0  # supera el límite por archivo → rechazado
