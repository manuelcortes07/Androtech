"""Blueprint de cuenta / perfil (refactor B1).

Perfil del taller logueado: ver datos, cambiar contraseña/email, datos de
facturación (branding/IVA/acento) y logo (white-label). Comportamiento idéntico
al que tenían en app.py; sólo cambia el nombre de endpoint (perfil → cuenta.perfil,
etc.).
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import select, text
from werkzeug.security import check_password_hash, generate_password_hash

import tokens as account_tokens
import uploads
from audit import registrar_auditoria
from auth import login_required
from avisos import SETTING_AVISOS, taller_avisos_activos
from database import get_session
from models import Usuario
from services import notificador
from settings import set_setting
from uploads import allowed_file, es_imagen_valida
from utils.security import csrf_protect, email_valido, validar_contraseña

logger = logging.getLogger("androtech")

bp = Blueprint("cuenta", __name__)


@bp.route("/perfil")
@login_required
def perfil():
    with get_session() as s:
        taller = s.execute(
            text("SELECT nombre, email_contacto, email_verificado FROM talleres "
                 "WHERE id = :t"), {"t": session.get("taller_id")},
        ).mappings().first()
    # B4: estado del interruptor de avisos automáticos al cliente (default on).
    return render_template("perfil.html", taller=taller,
                           notif_avisos_activos=taller_avisos_activos())


@bp.route("/perfil/notificaciones", methods=["POST"])
@login_required
@csrf_protect
def cambiar_notificaciones():
    """Activa/desactiva los avisos automáticos por email del taller (B4).

    Interruptor por taller (TallerSetting, auto-scoped). Si se desactiva, el
    punto único `avisos.avisar_cambio_estado` deja de enviar para este taller.
    """
    activar = request.form.get("avisos") == "on"
    set_setting(SETTING_AVISOS, "1" if activar else "0")
    registrar_auditoria("notif_avisos_toggle", session["usuario"],
                        {"taller_id": session.get("taller_id"),
                         "activas": activar})
    flash("Avisos automáticos al cliente "
          + ("activados." if activar else "desactivados."), "success")
    return redirect(url_for("cuenta.perfil"))


@bp.route("/perfil/password", methods=["POST"])
@login_required
@csrf_protect
def cambiar_password():
    actual = request.form.get("actual", "")
    nueva = request.form.get("nueva", "")
    with get_session() as s:
        # Auto-scoped al taller del usuario logueado (g.taller_id == sesión).
        user = s.scalars(
            select(Usuario).where(Usuario.usuario == session["usuario"])
        ).first()
        if not user or not check_password_hash(user.password, actual):
            flash("La contraseña actual no es correcta.", "danger")
            return redirect(url_for("cuenta.perfil"))
        ok, msg = validar_contraseña(nueva)
        if not ok:
            flash(msg, "danger")
            return redirect(url_for("cuenta.perfil"))
        user.password = generate_password_hash(nueva)
        s.commit()
    registrar_auditoria("password_cambiado", session["usuario"],
                        {"taller_id": session.get("taller_id")})
    flash("Contraseña actualizada correctamente.", "success")
    return redirect(url_for("cuenta.perfil"))


@bp.route("/perfil/email", methods=["POST"])
@login_required
@csrf_protect
def cambiar_email():
    nuevo = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    if not email_valido(nuevo):
        flash("Introduce un email válido.", "danger")
        return redirect(url_for("cuenta.perfil"))
    tid = session.get("taller_id")
    with get_session() as s:
        user = s.scalars(
            select(Usuario).where(Usuario.usuario == session["usuario"])
        ).first()
        if not user or not check_password_hash(user.password, password):
            flash("La contraseña no es correcta.", "danger")
            return redirect(url_for("cuenta.perfil"))
        # Email único a nivel PLATAFORMA (ningún OTRO taller puede tenerlo).
        existe = s.execute(
            text("SELECT 1 FROM talleres WHERE lower(email_contacto) = :e "
                 "AND id != :t"), {"e": nuevo, "t": tid},
        ).first()
        if existe:
            flash("Ese email ya está en uso por otra cuenta.", "danger")
            return redirect(url_for("cuenta.perfil"))
        # Cambiar el email → vuelve a NO verificado.
        s.execute(
            text("UPDATE talleres SET email_contacto = :e, email_verificado = 0 "
                 "WHERE id = :t"), {"e": nuevo, "t": tid},
        )
        s.commit()
    # Reenviar verificación al nuevo email (reusa B3.2).
    try:
        tok = account_tokens.generar_token_verificacion(tid, nuevo)
        url = url_for("auth.verificar_email", token=tok, _external=True)
        notificador.enviar_email("send_email_verificacion", nuevo, url, None)
    except Exception as e:
        logger.error(json.dumps({"event": "cambiar_email_verif_error",
                                 "error": str(e)}, ensure_ascii=False))
    registrar_auditoria("email_cambiado", session["usuario"],
                        {"taller_id": tid, "nuevo_email": nuevo})
    flash("Email actualizado. Te hemos enviado un enlace para verificarlo.",
          "success")
    return redirect(url_for("cuenta.perfil"))


@bp.route("/perfil/taller", methods=["POST"])
@login_required
@csrf_protect
def cambiar_datos_taller():
    """Datos de facturación del taller (emisor de los documentos).

    Actualiza columnas propias (nombre, direccion, telefono, nif) + claves de
    branding en `config` (iva_rate, moneda, web). Auto-scoped al taller logueado
    (UPDATE ... WHERE id = session taller_id).
    """
    tid = session.get("taller_id")
    nombre = (request.form.get("nombre") or "").strip()
    if not nombre:
        flash("El nombre del taller no puede estar vacío.", "danger")
        return redirect(url_for("cuenta.perfil"))
    direccion = (request.form.get("direccion") or "").strip()
    telefono = (request.form.get("telefono") or "").strip()
    nif = (request.form.get("nif") or "").strip()
    web = (request.form.get("web") or "").strip()
    moneda = (request.form.get("moneda") or "EUR").strip() or "EUR"
    # IVA llega en % (0–100) → se guarda como fracción (0.21).
    try:
        iva_pct = float(request.form.get("iva", "21") or 21)
    except ValueError:
        iva_pct = 21.0
    iva_pct = min(max(iva_pct, 0.0), 100.0)

    with get_session() as s:
        row = s.execute(text("SELECT config FROM talleres WHERE id = :t"),
                        {"t": tid}).mappings().first()
        try:
            cfg = json.loads(row["config"]) if row and row["config"] else {}
        except (ValueError, TypeError):
            cfg = {}
        cfg["iva_rate"] = round(iva_pct / 100.0, 4)
        cfg["moneda"] = moneda
        cfg["web"] = web
        # Color de acento del taller (sólo superficies del cliente). Sólo se
        # guarda si es un hex #RRGGBB válido; vacío/incorrecto → se quita.
        accent = (request.form.get("accent_color") or "").strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
            cfg["accent_color"] = accent
        else:
            cfg.pop("accent_color", None)
        s.execute(
            text("UPDATE talleres SET nombre = :n, direccion = :d, telefono = :tel, "
                 "nif = :nif, config = :cfg WHERE id = :t"),
            {"n": nombre, "d": direccion, "tel": telefono, "nif": nif,
             "cfg": json.dumps(cfg, ensure_ascii=False), "t": tid},
        )
        s.commit()
    registrar_auditoria("datos_taller_actualizados", session["usuario"],
                        {"taller_id": tid})
    flash("Datos del taller actualizados. Ya aparecen en tus documentos.",
          "success")
    return redirect(url_for("cuenta.perfil"))


def _set_logo_file(tid, nuevo_nombre):
    """Escribe (o limpia con None) config.logo_file del taller y devuelve el
    nombre del logo ANTERIOR (para borrar su fichero). Auto-scoped por id."""
    with get_session() as s:
        row = s.execute(text("SELECT config FROM talleres WHERE id = :t"),
                        {"t": tid}).mappings().first()
        try:
            cfg = json.loads(row["config"]) if row and row["config"] else {}
        except (ValueError, TypeError):
            cfg = {}
        anterior = cfg.get("logo_file")
        if nuevo_nombre:
            cfg["logo_file"] = nuevo_nombre
        else:
            cfg.pop("logo_file", None)
        s.execute(text("UPDATE talleres SET config = :c WHERE id = :t"),
                  {"c": json.dumps(cfg, ensure_ascii=False), "t": tid})
        s.commit()
    return anterior


@bp.route("/perfil/logo", methods=["POST"])
@login_required
@csrf_protect
def subir_logo_taller():
    """Sube/reemplaza el logo del taller (white-label). Reutiliza la validación
    segura de subidas (magic bytes + allowlist sin SVG + límite 5 MB)."""
    tid = session.get("taller_id")
    logo = request.files.get("logo")
    if not (logo and logo.filename and allowed_file(logo.filename)
            and es_imagen_valida(logo)):
        flash("Logo no válido. Usa PNG, JPG, WebP o GIF (máx. 5 MB).", "danger")
        return redirect(url_for("cuenta.perfil"))
    ext = logo.filename.rsplit(".", 1)[1].lower()
    unique_name = f"logo_{tid}_{secrets.token_hex(8)}.{ext}"
    logo.save(os.path.join(uploads.LOGO_FOLDER, unique_name))
    anterior = _set_logo_file(tid, unique_name)
    # Borrar el logo anterior (si lo había) para no acumular ficheros huérfanos.
    if anterior and anterior != unique_name:
        try:
            os.remove(os.path.join(uploads.LOGO_FOLDER, anterior))
        except OSError:
            pass
    registrar_auditoria("logo_taller_actualizado", session["usuario"],
                        {"taller_id": tid})
    flash("Logo actualizado. Ya aparece en tu portal y documentos.", "success")
    return redirect(url_for("cuenta.perfil"))


@bp.route("/perfil/logo/eliminar", methods=["POST"])
@login_required
@csrf_protect
def eliminar_logo_taller():
    """Quita el logo del taller (vuelve al nombre textual como fallback)."""
    tid = session.get("taller_id")
    anterior = _set_logo_file(tid, None)
    if anterior:
        try:
            os.remove(os.path.join(uploads.LOGO_FOLDER, anterior))
        except OSError:
            pass
    registrar_auditoria("logo_taller_eliminado", session["usuario"],
                        {"taller_id": tid})
    flash("Logo eliminado. Se usará el nombre del taller.", "info")
    return redirect(url_for("cuenta.perfil"))
