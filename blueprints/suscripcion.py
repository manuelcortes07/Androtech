"""Blueprint de suscripcion del SaaS (Fase 3b, refactor B1).

Registro self-service (signup), hub de facturacion del taller, pagina de bloqueo
por impago, portal de Stripe y el WEBHOOK de la suscripcion (saas_webhook). Es el
flujo en que la plataforma cobra a los talleres (StripeClient dedicado en
saas_billing) -- SEPARADO del pago de reparaciones (blueprints/pagos.py). NUNCA
se mezclan. Comportamiento identico al que tenian en app.py; solo cambia el
nombre de endpoint (signup -> suscripcion.signup, saas_webhook ->
suscripcion.saas_webhook, etc.).

La PUERTA de suscripcion (puerta_suscripcion + _GATE_EXENTAS) sigue en app.py:
es un before_request que debe correr para TODAS las peticiones. El webhook
conserva sus garantias: exencion CSRF (_CSRF_EXENTAS en app.py), firma propia
(STRIPE_SAAS_WEBHOOK_SECRET), idempotencia (ledger stripe_eventos) y validacion
del taller_id de la metadata.
"""

from __future__ import annotations

import json
import logging
import re as _re
from datetime import datetime

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import text
from werkzeug.security import generate_password_hash

import saas_billing
import tokens as account_tokens
from audit import registrar_auditoria
from auth import login_required, obtener_permisos_usuario
from database import get_session, insert_or_ignore
from extensions import limiter
from models import StripeEvento
from services import notificador
from utils.security import csrf_protect, email_valido, validar_contraseña

logger = logging.getLogger("androtech")

bp = Blueprint("suscripcion", __name__)


# _email_valido se traslado a utils.security.email_valido (B1); alias local.
_email_valido = email_valido


def _slugify(nombre: str) -> str:
    """Convierte el nombre del taller en un slug URL-safe."""
    base = nombre.strip().lower()
    base = base.replace("ñ", "n")
    # quita acentos básicos
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        base = base.replace(a, b)
    base = _re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base or "taller"


def _slug_unico(base: str) -> str:
    """Devuelve un slug que no colisiona con otro taller (base, base-2, …)."""
    with get_session() as s:
        existentes = set(s.execute(text("SELECT slug FROM talleres")).scalars().all())
    if base not in existentes:
        return base
    i = 2
    while f"{base}-{i}" in existentes:
        i += 1
    return f"{base}-{i}"


# _email_valido se trasladó a utils.security.email_valido (B1); alias local.
_email_valido = email_valido


def _sval(obj, key):
    """Lee un campo de un objeto Stripe (atributo) o de un dict (mock/test)."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


@bp.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
@csrf_protect
def signup():
    """Alta self-service de un taller nuevo: crea Taller + admin + Stripe
    Customer y arranca un Checkout de suscripción (trial 14 días, tarjeta
    requerida). Transacción: si Stripe falla, NO quedan talleres a medias.
    """
    if request.method == "GET":
        return render_template("signup.html")

    nombre = request.form.get("nombre_taller", "").strip()
    email = request.form.get("email", "").strip().lower()
    admin_user = request.form.get("usuario", "").strip()
    password = request.form.get("password", "")

    errores = []
    if not nombre:
        errores.append("El nombre del taller es obligatorio.")
    if not _email_valido(email):
        errores.append("Introduce un email válido.")
    if not admin_user:
        errores.append("El usuario administrador es obligatorio.")
    _ok_pwd, _msg_pwd = validar_contraseña(password)
    if not _ok_pwd:
        errores.append(_msg_pwd)
    if errores:
        for e in errores:
            flash(e, "danger")
        return render_template("signup.html", nombre=nombre, email=email,
                               usuario=admin_user), 400

    # Email único a nivel PLATAFORMA (talleres no lleva scope de taller).
    with get_session() as s:
        ya = s.execute(
            text("SELECT 1 FROM talleres WHERE lower(email_contacto) = :e"),
            {"e": email},
        ).first()
    if ya:
        flash("Ya existe una cuenta con ese email.", "danger")
        return render_template("signup.html", nombre=nombre, usuario=admin_user), 400

    slug = _slug_unico(_slugify(nombre))

    # 1) Stripe Customer PRIMERO (si falla, no se crea nada en BD).
    customer_id = None
    if saas_billing.is_configured():
        try:
            cust = saas_billing.crear_customer(email, nombre)
            customer_id = _sval(cust, "id")
        except Exception as e:
            logger.error(json.dumps({"event": "signup_stripe_customer_error",
                                     "error": str(e)}, ensure_ascii=False))
            flash("No se pudo iniciar el alta con la pasarela de pago. "
                  "Inténtalo de nuevo en unos minutos.", "danger")
            return render_template("signup.html", nombre=nombre, email=email,
                                   usuario=admin_user), 502

    # 2) Taller + admin + (opcional) Checkout en UNA transacción. Si el Checkout
    #    falla, el `with` sale por excepción SIN commit → rollback total.
    trial_fin = saas_billing.trial_fin_str()
    checkout_url = None
    nuevo_tid = None
    try:
        with get_session() as s:
            nuevo_tid = s.execute(
                text("""INSERT INTO talleres
                        (nombre, slug, email_contacto, fecha_alta, estado, plan,
                         stripe_customer_id, trial_fin)
                        VALUES (:n, :sl, :e, :fa, 'trial', 'basico', :cust, :tf)
                        RETURNING id"""),
                {"n": nombre, "sl": slug, "e": email,
                 "fa": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "cust": customer_id, "tf": trial_fin},
            ).scalar()
            s.execute(
                text('INSERT INTO usuarios (taller_id, usuario, "contraseña", rol) '
                     'VALUES (:tid, :u, :p, \'admin\')'),
                {"tid": nuevo_tid, "u": admin_user,
                 "p": generate_password_hash(password)},
            )
            s.flush()
            if saas_billing.is_configured():
                checkout = saas_billing.crear_checkout_suscripcion(
                    customer_id, nuevo_tid,
                    success_url=url_for("dashboard", _external=True),
                    cancel_url=url_for("suscripcion.suscripcion", _external=True),
                )
                checkout_url = _sval(checkout, "url")
            s.commit()
    except Exception as e:
        logger.error(json.dumps({"event": "signup_error", "slug": slug,
                                 "error": str(e)}, ensure_ascii=False))
        flash("No se pudo completar el alta. No se ha creado ninguna cuenta; "
              "inténtalo de nuevo.", "danger")
        return render_template("signup.html", nombre=nombre, email=email,
                               usuario=admin_user), 502

    # Auditoría de plataforma (taller_id explícito; evento del nuevo taller).
    registrar_auditoria("signup_taller", admin_user,
                        {"taller_id": nuevo_tid, "slug": slug, "email": email})

    # B3.2: enviar verificación de email (NO bloqueante; el taller ya puede usar
    # la app durante el trial, con un aviso para verificar).
    try:
        _vtoken = account_tokens.generar_token_verificacion(nuevo_tid, email)
        _vurl = url_for("auth.verificar_email", token=_vtoken, _external=True)
        notificador.enviar_email("send_email_verificacion", email, _vurl, nombre)
    except Exception as e:
        logger.error(json.dumps({"event": "signup_verif_email_error",
                                 "error": str(e)}, ensure_ascii=False))

    # Log in inmediato: el taller entra en 'trial' y puede usar la app.
    session["usuario"] = admin_user
    session["rol"] = "admin"
    session["permisos"] = obtener_permisos_usuario("admin")
    session["taller_id"] = nuevo_tid
    session["taller_slug"] = slug

    if checkout_url:
        # A Stripe Checkout a por la tarjeta (requerida durante el trial).
        return redirect(checkout_url)
    flash("¡Bienvenido a Kintsu! Tu prueba de 14 días está activa.", "success")
    return redirect(url_for("dashboard"))


@bp.route("/suscripcion")
@login_required
def suscripcion():
    """Hub de facturación del taller: estado de la suscripción y gestión.

    El botón al Stripe Customer Portal se añade en 3b.5.
    """
    with get_session() as s:
        taller = s.execute(
            text("SELECT id, nombre, estado, trial_fin, stripe_customer_id "
                 "FROM talleres WHERE id = :tid"),
            {"tid": session.get("taller_id")},
        ).mappings().first()
    return render_template("suscripcion.html", taller=taller)


@bp.route("/suscripcion/bloqueado")
def suscripcion_bloqueado():
    """Página mostrada cuando la suscripción del taller no está activa.

    NO borra ni expone datos: sólo informa y enlaza al pago/gestión. Los datos
    del taller siguen intactos y se recuperan en cuanto regulariza el pago.
    """
    estado = None
    tid = session.get("taller_id")
    if tid:
        with get_session() as s:
            row = s.execute(
                text("SELECT estado FROM talleres WHERE id = :t"), {"t": tid}
            ).first()
            estado = row[0] if row else None
    return render_template("suscripcion_bloqueado.html", estado=estado), 402


@bp.route("/suscripcion/portal")
@login_required
def suscripcion_portal():
    """Redirige al Stripe Customer Portal para gestionar pago/cancelación (3b.5)."""
    with get_session() as s:
        row = s.execute(
            text("SELECT stripe_customer_id FROM talleres WHERE id = :tid"),
            {"tid": session.get("taller_id")},
        ).first()
    customer_id = row[0] if row else None
    if not customer_id or not saas_billing.is_configured():
        flash("Aún no hay un método de pago asociado a tu cuenta.", "info")
        return redirect(url_for("suscripcion.suscripcion"))
    try:
        portal = saas_billing.crear_portal(
            customer_id, return_url=url_for("suscripcion.suscripcion", _external=True)
        )
        return redirect(_sval(portal, "url"))
    except Exception as e:
        logger.error(json.dumps({"event": "portal_error", "error": str(e)},
                                ensure_ascii=False))
        flash("No se pudo abrir el portal de gestión. Inténtalo más tarde.", "danger")
        return redirect(url_for("suscripcion.suscripcion"))


def _taller_por_customer(s, customer_id):
    """taller_id cuyo stripe_customer_id coincide, o None. SQL crudo (talleres
    no lleva scope de taller)."""
    if not customer_id:
        return None
    row = s.execute(
        text("SELECT id FROM talleres WHERE stripe_customer_id = :c"),
        {"c": customer_id},
    ).first()
    return row[0] if row else None


def _saas_aplicar_evento(s, etype, obj):
    """Aplica un evento de suscripción al Taller. Devuelve (taller_id,
    nuevo_estado, sub_id). NO toca reparaciones ni ningún dato de cliente."""
    customer_id = obj.get("customer")
    tid = _taller_por_customer(s, customer_id)
    if tid is None and etype == "checkout.session.completed":
        meta = obj.get("metadata") or {}
        if meta.get("taller_id"):
            try:
                tid = int(meta["taller_id"])
            except (TypeError, ValueError):
                tid = None
    if tid is None:
        return None, None, None

    nuevo_estado = None
    sub_id = None
    if etype == "checkout.session.completed":
        sub_id = obj.get("subscription")
        nuevo_estado = "trial"  # alta completada con tarjeta; sigue en prueba
    elif etype == "customer.subscription.updated":
        sub_id = obj.get("id")
        nuevo_estado = saas_billing.estado_por_status_stripe(obj.get("status"))
    elif etype == "customer.subscription.deleted":
        sub_id = obj.get("id")
        nuevo_estado = "cancelado"   # suscripción eliminada → acceso bloqueado
    elif etype == "invoice.payment_failed":
        nuevo_estado = "suspendido"  # política: impago → bloqueo (datos intactos)
    elif etype == "invoice.paid":
        # Reactivar SÓLO si estaba suspendido (no degrada un trial al pagar el
        # invoice de 0 € del inicio de prueba).
        cur = s.execute(text("SELECT estado FROM talleres WHERE id = :t"),
                        {"t": tid}).scalar()
        if cur == "suspendido":
            nuevo_estado = "activo"
    else:
        return tid, None, None  # evento no manejado

    if nuevo_estado is None:
        return tid, None, sub_id

    sets = ["estado = :est"]
    params = {"t": tid, "est": nuevo_estado}
    if sub_id:
        sets.append("stripe_sub_id = :sub")
        params["sub"] = sub_id
    s.execute(text(f"UPDATE talleres SET {', '.join(sets)} WHERE id = :t"), params)
    return tid, nuevo_estado, sub_id


@bp.route("/saas/webhook", methods=["POST"])
def saas_webhook():
    """Webhook de la SUSCRIPCIÓN del SaaS — SEPARADO del de reparaciones.

    - Verifica la firma con STRIPE_SAAS_WEBHOOK_SECRET (saas_billing).
    - Idempotente: el `event_id` se inserta en `stripe_eventos` dentro de la
      MISMA transacción que el efecto; si Stripe reenvía el evento, el UNIQUE
      choca y no se repite nada.
    - Sincroniza Taller.estado. NUNCA toca reparaciones.
    """
    payload = request.data
    sig = request.headers.get("Stripe-Signature")

    if not saas_billing.STRIPE_SAAS_WEBHOOK_SECRET:
        logger.error("[SAAS-WEBHOOK] STRIPE_SAAS_WEBHOOK_SECRET no configurado")
        return jsonify({"error": "SaaS webhook secret not configured"}), 400
    if not sig:
        return jsonify({"error": "Missing Stripe-Signature header"}), 400

    try:
        event = saas_billing.construir_evento(payload, sig)
    except Exception as e:
        logger.error(json.dumps({"event": "saas_webhook_bad_signature",
                                 "error": str(e)}, ensure_ascii=False))
        return jsonify({"error": str(e)}), 400

    etype = event.get("type")
    eid = event.get("id")
    obj = (event.get("data") or {}).get("object", {}) or {}

    try:
        with get_session() as s:
            # Guarda de idempotencia + efecto en una sola transacción.
            ins = s.execute(
                insert_or_ignore(StripeEvento)
                .values(event_id=eid, tipo=etype,
                        recibido_en=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                .on_conflict_do_nothing()
            )
            if eid and ins.rowcount == 0:
                s.rollback()
                logger.info(json.dumps({"event": "saas_webhook_duplicate",
                                        "stripe_event": eid}, ensure_ascii=False))
                return jsonify({"status": "duplicate"}), 200

            taller_id, nuevo_estado, sub_id = _saas_aplicar_evento(s, etype, obj)
            if taller_id is not None:
                s.execute(
                    text("UPDATE stripe_eventos SET taller_id = :t WHERE event_id = :e"),
                    {"t": taller_id, "e": eid},
                )
            s.commit()
    except Exception as e:
        logger.error(json.dumps({"event": "saas_webhook_error", "type": etype,
                                 "error": str(e)}, ensure_ascii=False))
        return jsonify({"error": str(e)}), 500

    if taller_id is not None and nuevo_estado is not None:
        registrar_auditoria(f"saas_{etype}", "stripe",
                            {"taller_id": taller_id, "estado": nuevo_estado,
                             "subscription": sub_id},
                            taller_id=taller_id)
        logger.info(json.dumps({"event": "saas_webhook_processed", "type": etype,
                                "taller_id": taller_id, "estado": nuevo_estado},
                               ensure_ascii=False))
    return jsonify({"status": "ok"}), 200
