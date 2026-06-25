"""Blueprint de autenticación (refactor B1).

Rutas: login, logout, reset de contraseña (B3.1) y verificación de email (B3.2).
Comportamiento idéntico al que tenían en app.py; sólo cambia el nombre de
endpoint (login → auth.login, etc.) y por eso las exenciones de la puerta de
suscripción (_GATE_EXENTAS) usan ya los nombres con prefijo.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from itsdangerous import BadSignature, SignatureExpired
from sqlalchemy import select, text
from werkzeug.security import check_password_hash, generate_password_hash

import tokens as account_tokens
from audit import registrar_auditoria
from auth import login_required, obtener_permisos_usuario
from database import get_session
from extensions import limiter
from models import Usuario
from services import notificador
from utils.security import csrf_protect, validar_contraseña

logger = logging.getLogger("androtech")

bp = Blueprint("auth", __name__)


# LOGIN
@bp.route("/login", methods=["GET", "POST"])
@bp.route("/t/<slug>/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
@csrf_protect
def login(slug=None):
    if request.method == "POST":
        usuario = request.form["usuario"]
        contraseña = request.form["contraseña"]

        # Fase 2.2 (riesgo 🔴 #4): el usuario se busca por (taller_id, usuario),
        # no solo por usuario. g.taller_id lo ha resuelto el before_request
        # (desde el slug /t/{slug}/login o por defecto el taller 1).
        with get_session() as s:
            user = s.scalars(
                select(Usuario).where(
                    Usuario.usuario == usuario,
                    Usuario.taller_id == g.taller_id,
                )
            ).first()

        if user and check_password_hash(user.password, contraseña):
            # H7: regenera la sesión tras autenticar (anti session-fixation).
            # Descarta cualquier dato de una sesión previa; se repuebla de cero
            # y los permisos se cargan FRESCOS desde el rol.
            session.clear()
            session["usuario"] = user.usuario
            session["rol"] = user.rol
            session["permisos"] = obtener_permisos_usuario(user.rol)
            # Ligar la sesión al taller del usuario (fuente de verdad de las
            # rutas internas en las siguientes peticiones).
            session["taller_id"] = user.taller_id
            session["taller_slug"] = g.taller_slug
            # H1: flag de superadmin de plataforma (edita roles globales).
            session["es_superadmin"] = bool(getattr(user, "es_superadmin", 0))
            flash(f"Bienvenido, {user.usuario}!", "success")

            # Registrar auditoría
            registrar_auditoria('login', user.usuario, {
                'rol': user.rol,
                'ip': request.remote_addr
            }, ip_address=request.remote_addr)

            try:
                logger.info(json.dumps({
                    "event": "login_success",
                    "user": user.usuario,
                    "role": user.rol,
                    "ip": request.remote_addr
                }, ensure_ascii=False))
            except Exception:
                logger.info(f"login_success user={user.usuario}")

            return redirect(url_for("dashboard.dashboard"))
        else:
            flash("Usuario o contraseña incorrectos.", "danger")

            # Registrar intento fallido
            registrar_auditoria('login_failed', usuario or 'unknown', {
                'ip': request.remote_addr
            }, ip_address=request.remote_addr)

            try:
                logger.warning(json.dumps({
                    "event": "login_failed",
                    "user": usuario,
                    "ip": request.remote_addr
                }, ensure_ascii=False))
            except Exception:
                logger.warning(f"login_failed user={usuario}")

    return render_template("login.html")


# LOGOUT
@bp.route("/logout")
@login_required
def logout():
    session.clear()
    flash("Has cerrado sesión correctamente.", "info")
    return redirect(url_for("auth.login"))


# =========================================
# 🔸 RESET DE CONTRASEÑA (B3.1)
# =========================================
# El email vive en talleres.email_contacto (el del admin del taller). El reset
# localiza el taller por email y opera sobre SU usuario admin. SQL crudo a
# propósito: el usuario no está logueado (g.taller_id sería el default), así que
# no debemos pasar por el filtro automático del ORM.
_MSG_RESET_GENERICO = ("Si ese email corresponde a una cuenta, te hemos enviado "
                       "un enlace para restablecer la contraseña.")


@bp.route("/reset", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])  # anti-abuso
@csrf_protect
def reset_solicitar():
    if request.method == "GET":
        return render_template("reset_solicitar.html")

    email = request.form.get("email", "").strip().lower()
    # ANTI-ENUMERACIÓN: la respuesta es SIEMPRE la misma, exista o no el email.
    with get_session() as s:
        taller = s.execute(
            text("SELECT id, nombre, email_contacto FROM talleres "
                 "WHERE lower(email_contacto) = :e"),
            {"e": email},
        ).mappings().first()
        if taller:
            urow = s.execute(
                text('SELECT id, taller_id, "contraseña" AS pw FROM usuarios '
                     "WHERE taller_id = :t AND rol = 'admin' ORDER BY id LIMIT 1"),
                {"t": taller["id"]},
            ).mappings().first()
            if urow:
                usuario = SimpleNamespace(id=urow["id"], taller_id=urow["taller_id"],
                                          password=urow["pw"])
                token = account_tokens.generar_token_reset(usuario)
                reset_url = url_for("auth.reset_confirmar", token=token, _external=True)
                try:
                    notificador.enviar_email("send_password_reset",
                        taller["email_contacto"], reset_url, taller["nombre"])
                except Exception as e:
                    logger.error(json.dumps({"event": "reset_email_error",
                                             "error": str(e)}, ensure_ascii=False))
                registrar_auditoria("password_reset_solicitado", str(urow["id"]),
                                    {"taller_id": taller["id"]},
                                    taller_id=taller["id"])
    flash(_MSG_RESET_GENERICO, "info")
    return render_template("reset_solicitar.html", enviado=True)


@bp.route("/reset/<token>", methods=["GET", "POST"])
@csrf_protect
def reset_confirmar(token):
    # Validar firma + caducidad. Token manipulado o caducado → fuera.
    try:
        datos = account_tokens.cargar_token_reset(token)
    except SignatureExpired:
        flash("El enlace de restablecimiento ha caducado. Solicita uno nuevo.", "danger")
        return redirect(url_for("auth.reset_solicitar"))
    except BadSignature:
        flash("El enlace de restablecimiento no es válido.", "danger")
        return redirect(url_for("auth.reset_solicitar"))

    uid, tid, fp = datos.get("uid"), datos.get("tid"), datos.get("fp")
    with get_session() as s:
        urow = s.execute(
            text('SELECT id, "contraseña" AS pw FROM usuarios '
                 "WHERE id = :uid AND taller_id = :tid"),
            {"uid": uid, "tid": tid},
        ).mappings().first()
    # Single-use de facto: si la contraseña ya cambió, la huella no coincide.
    if not urow or account_tokens.huella_password(urow["pw"]) != fp:
        flash("El enlace ya no es válido (quizá la contraseña ya se cambió).", "danger")
        return redirect(url_for("auth.reset_solicitar"))

    if request.method == "GET":
        return render_template("reset_confirmar.html", token=token)

    nueva = request.form.get("password", "")
    ok, msg = validar_contraseña(nueva)
    if not ok:
        flash(msg, "danger")
        return render_template("reset_confirmar.html", token=token), 400
    with get_session() as s:
        s.execute(
            text('UPDATE usuarios SET "contraseña" = :p WHERE id = :uid AND taller_id = :tid'),
            {"p": generate_password_hash(nueva), "uid": uid, "tid": tid},
        )
        s.commit()
    registrar_auditoria("password_reset_completado", str(uid),
                        {"taller_id": tid}, taller_id=tid)
    flash("Contraseña actualizada. Ya puedes iniciar sesión.", "success")
    return redirect(url_for("auth.login"))


# =========================================
# 🔸 VERIFICACIÓN DE EMAIL (B3.2) — NO bloqueante
# =========================================
@bp.route("/verificar-email/<token>")
def verificar_email(token):
    try:
        datos = account_tokens.cargar_token_verificacion(token)
    except (BadSignature, SignatureExpired):
        flash("El enlace de verificación no es válido o ha caducado.", "danger")
        return redirect(url_for("auth.login"))
    tid, fp = datos.get("tid"), datos.get("fp")
    with get_session() as s:
        row = s.execute(
            text("SELECT email_contacto FROM talleres WHERE id = :t"), {"t": tid}
        ).first()
        # Si el email cambió desde que se emitió el enlace, la huella no casa.
        if not row or account_tokens.huella_email(row[0]) != fp:
            flash("El enlace de verificación ya no es válido.", "danger")
            return redirect(url_for("auth.login"))
        s.execute(text("UPDATE talleres SET email_verificado = 1 WHERE id = :t"),
                  {"t": tid})
        s.commit()
    registrar_auditoria("email_verificado", "sistema", {"taller_id": tid},
                        taller_id=tid)
    flash("¡Email verificado correctamente! Gracias.", "success")
    return redirect(url_for("dashboard.dashboard") if session.get("usuario")
                    else url_for("auth.login"))


@bp.route("/verificar-email/reenviar", methods=["POST"])
@login_required
@limiter.limit("3 per hour", methods=["POST"])
@csrf_protect
def reenviar_verificacion():
    tid = session.get("taller_id")
    with get_session() as s:
        row = s.execute(
            text("SELECT nombre, email_contacto, email_verificado FROM talleres "
                 "WHERE id = :t"), {"t": tid}
        ).mappings().first()
    if row and not row["email_verificado"] and row["email_contacto"]:
        try:
            tok = account_tokens.generar_token_verificacion(tid, row["email_contacto"])
            url = url_for("auth.verificar_email", token=tok, _external=True)
            notificador.enviar_email("send_email_verificacion", row["email_contacto"], url, row["nombre"])
        except Exception as e:
            logger.error(json.dumps({"event": "reenvio_verif_error",
                                     "error": str(e)}, ensure_ascii=False))
    flash("Si tu email está pendiente de verificar, te hemos reenviado el enlace.",
          "info")
    return redirect(request.referrer or url_for("dashboard.dashboard"))
