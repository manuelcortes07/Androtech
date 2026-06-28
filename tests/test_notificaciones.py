"""Notificaciones automáticas al cliente por email (cambio de estado).

Cubre el disparador centralizado (`avisos.avisar_cambio_estado`) cableado en
`editar_reparacion`: que SALE el email al cambiar de estado, que NO sale sin
email, y — EL JUEZ aplicado a esta feature — que el email de un cambio en el
taller A NUNCA lleva el branding del taller B.

Reusa las fixtures del juez de aislamiento.
"""

import pytest

from tests.test_aislamiento import (  # noqa: F401
    admin_A,
    dos_talleres,
)


@pytest.fixture
def captura_email(monkeypatch):
    """Sustituye `_send` del EmailService singleton por un captador del html.

    Se parchea a nivel de INSTANCIA (como test_branding): un atributo de
    instancia ensombrece tanto el método de clase como el no-op del autouse
    `_block_external_services`, sea cual sea el orden de fixtures. Llamado como
    `self._send(subject=…, html_body=…)`, así que la firma es `**kwargs` (sin
    self). El html se renderiza ANTES de _send con el branding real (_emisor()).
    """
    cap = {}

    from services import email_service

    def _capt(**kwargs):
        cap["enviado"] = True
        cap["html"] = kwargs.get("html_body", "")
        cap["to"] = kwargs.get("to_email")
        cap["subject"] = kwargs.get("subject", "")

    monkeypatch.setattr(email_service, "_send", _capt)
    return cap


class TestAvisoCambioEstado:
    def test_cambio_de_estado_envia_email(self, admin_A, dos_talleres, captura_email):
        repA, cliA = dos_talleres["repA"], dos_talleres["cliA"]
        r = admin_A.post(f"/reparaciones/editar/{repA}", data={
            "cliente_id": cliA, "dispositivo": "iPhoneA",
            "descripcion": "normal de A", "estado": "En proceso",
            "precio": "100", "csrf_token": "tk",
        }, follow_redirects=False)
        assert r.status_code in (302, 303)
        # Salió el email al cliente del taller A.
        assert captura_email.get("enviado") is True
        assert captura_email.get("to") == "comun@x.com"

    def test_sin_email_no_envia(self, admin_A, dos_talleres, captura_email, db_conn):
        repA, cliA = dos_talleres["repA"], dos_talleres["cliA"]
        # El cliente de A se queda sin email → la guarda corta el envío.
        db_conn.execute("UPDATE clientes SET email = '' WHERE id = ?", (cliA,))
        db_conn.commit()
        r = admin_A.post(f"/reparaciones/editar/{repA}", data={
            "cliente_id": cliA, "dispositivo": "iPhoneA",
            "descripcion": "normal de A", "estado": "En proceso",
            "precio": "100", "csrf_token": "tk",
        }, follow_redirects=False)
        assert r.status_code in (302, 303)
        assert "enviado" not in captura_email  # no se intentó enviar

    def test_sin_cambio_real_no_envia(self, admin_A, dos_talleres, captura_email):
        repA, cliA = dos_talleres["repA"], dos_talleres["cliA"]
        # Mismo estado ('Pendiente' → 'Pendiente'): no hay cambio → no email.
        r = admin_A.post(f"/reparaciones/editar/{repA}", data={
            "cliente_id": cliA, "dispositivo": "iPhoneA",
            "descripcion": "normal de A", "estado": "Pendiente",
            "precio": "100", "csrf_token": "tk",
        }, follow_redirects=False)
        assert r.status_code in (302, 303)
        assert "enviado" not in captura_email


class TestJuezBrandingNotificacion:
    """EL JUEZ aplicado a la feature: un aviso del taller A jamás puede llevar el
    branding/datos del taller B."""

    def test_email_de_A_no_lleva_branding_de_B(self, admin_A, dos_talleres,
                                                captura_email, db_conn):
        repA, cliA = dos_talleres["repA"], dos_talleres["cliA"]
        nombre_A = db_conn.execute(
            "SELECT nombre FROM talleres WHERE id = 1"
        ).fetchone()["nombre"]

        admin_A.post(f"/reparaciones/editar/{repA}", data={
            "cliente_id": cliA, "dispositivo": "iPhoneA",
            "descripcion": "normal de A", "estado": "En proceso",
            "precio": "100", "csrf_token": "tk",
        }, follow_redirects=False)

        html = captura_email.get("html", "")
        assert captura_email.get("enviado") is True
        # El branding del taller dueño (A) viaja; el del rival (B='Rival') NUNCA.
        assert nombre_A in html
        assert "Rival" not in html
        assert "Rival" not in captura_email.get("subject", "")


class TestPlantillaWhiteLabel:
    """B2: el email incluye el botón de seguimiento (por código) y el enlace de
    baja, y ya NO filtra el contacto hardcodeado del desarrollador."""

    def test_email_incluye_seguimiento_baja_y_sin_fuga(self, admin_A, dos_talleres,
                                                       captura_email, db_conn):
        repA, cliA = dos_talleres["repA"], dos_talleres["cliA"]
        db_conn.execute(
            "UPDATE reparaciones SET codigo_publico = 'TRACK-A-1' WHERE id = ?", (repA,)
        )
        db_conn.commit()
        admin_A.post(f"/reparaciones/editar/{repA}", data={
            "cliente_id": cliA, "dispositivo": "iPhoneA",
            "descripcion": "normal de A", "estado": "En proceso",
            "precio": "100", "csrf_token": "tk",
        }, follow_redirects=False)
        html = captura_email.get("html", "")
        # Botón al portal de seguimiento por código + enlace de baja firmado.
        assert "consulta?codigo=TRACK-A-1" in html
        assert "/notificaciones/baja/" in html
        # Estado en lenguaje claro para el cliente ('En proceso' → 'En reparación').
        assert "En reparación" in html
        # Fuga white-label ARREGLADA: ni teléfono ni email del desarrollador.
        assert "manuelcortescontreras11@gmail.com" not in html
        assert "633 234 395" not in html


class TestGuardiaAntiFuga:
    """Red de seguridad anti-regresión: ninguna plantilla de email que ve el
    CLIENTE final puede contener datos de contacto PERSONALES hardcodeados. Si
    alguien vuelve a meter un teléfono/email del desarrollador, esto lo caza.
    (reset_password/verificar_email NO entran: van al admin del taller y pueden
    llevar la marca Kintsu de plataforma.)"""

    _CLIENTE_TEMPLATES = [
        "repair_status_update.html", "payment_confirmation.html",
        "nueva_reparacion.html", "bienvenida_cliente.html",
        "presupuesto_enviado.html",
    ]
    # Contacto personal del desarrollador + cualquier @gmail hardcodeado.
    _PROHIBIDO = ["633 234 395", "633234395", "manuelcortescontreras11", "@gmail.com"]

    def test_plantillas_cliente_sin_contacto_personal(self):
        import os
        base = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "templates", "emails")
        for nombre in self._CLIENTE_TEMPLATES:
            with open(os.path.join(base, nombre), encoding="utf-8") as f:
                contenido = f.read()
            for prohibido in self._PROHIBIDO:
                assert prohibido not in contenido, (
                    f"FUGA: la plantilla {nombre} contiene '{prohibido}' "
                    "hardcodeado (debe venir del taller emisor)."
                )


class TestJuezBrandingTodasLasPlantillas:
    """EL JUEZ extendido a TODAS las plantillas al cliente: renderizadas con el
    taller A activo, llevan el branding de A — nunca el de B ('Rival') ni el
    contacto del desarrollador."""

    def test_cada_email_solo_branding_del_taller_dueno(self, app, dos_talleres,
                                                       captura_email, db_conn):
        from flask import g

        from services import email_service
        nombre_A = db_conn.execute(
            "SELECT nombre FROM talleres WHERE id = 1"
        ).fetchone()["nombre"]

        renders = []
        with app.test_request_context():
            g.taller_id = 1
            g.taller_slug = "androtech"
            email_service.send_payment_confirmation("c@a.com", "Cli", 1, 10.0, "desc")
            renders.append(("payment", captura_email.get("html", "")))
            email_service.send_nueva_reparacion("c@a.com", "Cli", 1, "iPhone",
                                                "desc", "2026-01-01")
            renders.append(("nueva", captura_email.get("html", "")))
            email_service.send_bienvenida_cliente("c@a.com", "Cli")
            renders.append(("bienvenida", captura_email.get("html", "")))

        for etiqueta, html in renders:
            assert nombre_A in html, f"{etiqueta}: falta el branding del taller A"
            assert "Rival" not in html, f"{etiqueta}: filtra el branding de B"
            assert "manuelcortescontreras11" not in html, f"{etiqueta}: contacto dev"
            assert "633 234 395" not in html, f"{etiqueta}: teléfono dev"


class TestInterruptorTaller:
    """B4: el taller puede apagar los avisos automáticos desde /perfil; con el
    interruptor en off, no sale ningún email."""

    def test_taller_con_avisos_off_no_envia(self, admin_A, dos_talleres,
                                            captura_email):
        # Apagar el interruptor del taller A (POST sin 'avisos' = desactivar).
        r = admin_A.post("/perfil/notificaciones", data={"csrf_token": "tk"},
                         follow_redirects=False)
        assert r.status_code in (302, 303)
        repA, cliA = dos_talleres["repA"], dos_talleres["cliA"]
        admin_A.post(f"/reparaciones/editar/{repA}", data={
            "cliente_id": cliA, "dispositivo": "iPhoneA",
            "descripcion": "normal de A", "estado": "En proceso",
            "precio": "100", "csrf_token": "tk",
        }, follow_redirects=False)
        assert "enviado" not in captura_email

    def test_reactivar_vuelve_a_enviar(self, admin_A, dos_talleres, captura_email):
        admin_A.post("/perfil/notificaciones", data={"csrf_token": "tk"})  # off
        admin_A.post("/perfil/notificaciones",
                     data={"avisos": "on", "csrf_token": "tk"})  # on de nuevo
        repA, cliA = dos_talleres["repA"], dos_talleres["cliA"]
        admin_A.post(f"/reparaciones/editar/{repA}", data={
            "cliente_id": cliA, "dispositivo": "iPhoneA",
            "descripcion": "normal de A", "estado": "En proceso",
            "precio": "100", "csrf_token": "tk",
        }, follow_redirects=False)
        assert captura_email.get("enviado") is True


class TestBajaOptOut:
    """B3: el cliente se da de baja por un enlace firmado; tras la baja no recibe
    avisos, y un token manipulado no puede dar de baja a otro."""

    def test_baja_marca_al_cliente(self, client, dos_talleres, db_conn, app):
        cliA = dos_talleres["cliA"]
        with app.test_request_context():
            from tokens import generar_token_baja
            token = generar_token_baja(cliA, 1)
        r = client.get(f"/notificaciones/baja/{token}")
        assert r.status_code == 200
        acepta = db_conn.execute(
            "SELECT acepta_emails FROM clientes WHERE id = ?", (cliA,)
        ).fetchone()["acepta_emails"]
        assert acepta == 0

    def test_token_manipulado_no_da_de_baja(self, client, dos_talleres, db_conn, app):
        cliA = dos_talleres["cliA"]
        with app.test_request_context():
            from tokens import generar_token_baja
            token = generar_token_baja(cliA, 1)
        # Corromper la firma → no debe tocar nada.
        r = client.get(f"/notificaciones/baja/{token}xxx")
        assert r.status_code == 400
        acepta = db_conn.execute(
            "SELECT acepta_emails FROM clientes WHERE id = ?", (cliA,)
        ).fetchone()["acepta_emails"]
        assert acepta == 1  # sigue suscrito

    def test_cliente_de_baja_no_recibe_aviso(self, admin_A, dos_talleres,
                                             captura_email, db_conn):
        repA, cliA = dos_talleres["repA"], dos_talleres["cliA"]
        db_conn.execute("UPDATE clientes SET acepta_emails = 0 WHERE id = ?", (cliA,))
        db_conn.commit()
        admin_A.post(f"/reparaciones/editar/{repA}", data={
            "cliente_id": cliA, "dispositivo": "iPhoneA",
            "descripcion": "normal de A", "estado": "En proceso",
            "precio": "100", "csrf_token": "tk",
        }, follow_redirects=False)
        assert "enviado" not in captura_email  # la guarda de baja cortó el envío
