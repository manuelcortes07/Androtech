"""Blueprint público (refactor B1).

Escaparate del taller (index, sobre, servicios, contacto) y portal del cliente
(consulta por código, mis-reparaciones por email, solicitar reparación). El
taller se resuelve en el before_request (slug `/t/{slug}/...` o por el propio
código); el branding pintado es el del taller resuelto. Comportamiento idéntico
al que tenían estas rutas en app.py; sólo cambia el nombre de endpoint
(index → publico.index, consulta → publico.consulta, …).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import func, select, text

from database import get_session
from extensions import limiter
from models import Cliente, Reparacion, SolicitudReparacion
from tokens import cargar_token_baja
from utils.security import csrf_protect

logger = logging.getLogger("androtech")

bp = Blueprint("publico", __name__)


@bp.route("/")
def index():
    # Fase 2.4: SQL crudo → filtrado MANUAL por taller (el filtro automático del
    # ORM no alcanza las text()). tid = taller activo resuelto por el resolver.
    tp = {"tid": g.taller_id}
    with get_session() as s:
        total_clientes = s.execute(text("SELECT COUNT(*) FROM clientes WHERE taller_id = :tid"), tp).scalar()
        activas = s.execute(text("SELECT COUNT(*) FROM reparaciones WHERE taller_id = :tid AND estado != 'Terminado' AND estado != 'Entregado'"), tp).scalar()
        terminadas = s.execute(text("SELECT COUNT(*) FROM reparaciones WHERE taller_id = :tid AND (estado = 'Terminado' OR estado = 'Entregado')"), tp).scalar()
        ingresos = s.execute(text("SELECT COALESCE(SUM(precio), 0) FROM reparaciones WHERE taller_id = :tid AND (estado = 'Terminado' OR estado = 'Entregado')"), tp).scalar()
        # Desglose por estado para mini-panel del hero
        estados_count = {}
        for row in s.execute(text("SELECT estado, COUNT(*) as c FROM reparaciones WHERE taller_id = :tid GROUP BY estado"), tp).all():
            estados_count[row[0]] = row[1]
    return render_template("index.html",
        total_clientes=total_clientes,
        activas=activas,
        terminadas=terminadas,
        ingresos=ingresos,
        estados_count=estados_count
    )


# =========================================
# 🔸 SECCIÓN CONTACTO
# =========================================
@bp.route("/contacto", methods=["GET", "POST"])
@csrf_protect
def contacto():
    if request.method == "POST":
        nombre = request.form["nombre"]
        email = request.form["email"]
        telefono = request.form["telefono"]
        tipo = request.form["tipo"]
        # Se lee para EXIGIR el campo (400 si falta); el contenido se registra abajo.
        mensaje = request.form["mensaje"]

        try:
            logger.info(json.dumps({
                "event": "contacto_enviado",
                "nombre": nombre,
                "email": email,
                "telefono": telefono,
                "tipo": tipo,
                "mensaje": mensaje
            }, ensure_ascii=False))
        except Exception:
            logger.info(f"contacto_enviado nombre={nombre} email={email} tipo={tipo}")

        return render_template("contacto_exito.html", nombre=nombre)

    return render_template("contacto.html")


# =========================================
# 🔸 SECCIÓN SOBRE NOSOTROS
# =========================================
@bp.route("/sobre")
def sobre():
    return render_template("sobre_nosotros.html")


# =========================================
# 🔸 SECCIÓN SERVICIOS
# =========================================
@bp.route("/servicios")
def servicios():
    return render_template("servicios.html")


# =========================================
# 🔸 CONSULTA PÚBLICA DE REPARACIONES
# =========================================
@bp.route("/consulta", methods=["GET", "POST"])
@bp.route("/t/<slug>/consulta", methods=["GET", "POST"])
@limiter.limit("30 per minute", methods=["POST"])  # H3: defensa en profundidad
@csrf_protect
def consulta(slug=None):
    # H3: el portal localiza la reparación por su CÓDIGO PÚBLICO no adivinable
    # (enlace/QR del cliente o formulario), NUNCA por el id secuencial. El taller
    # lo resuelve el before_request: del slug /t/{slug}/... o del propio código.
    reparacion = None
    error = None

    # Enlace directo del cliente (QR): GET /consulta?codigo=XXXX
    codigo_get = request.args.get('codigo', '').strip()

    if request.method == "POST" or codigo_get:
        # UX de tecleo: tolera espacios (un código válido NUNCA los lleva, así que
        # quitar TODO el whitespace es seguro). NO se normaliza mayúsc./minúsc.:
        # el código es case-SENSITIVE (token_urlsafe) y la resolución H3 no cambia.
        codigo = "".join((request.form.get("codigo") or codigo_get).split())
        if not codigo:
            error = "Por favor, introduce tu código de seguimiento."
        else:
            with get_session() as s:
                reparacion = s.execute(
                    select(
                        Reparacion.id, Reparacion.dispositivo,
                        Reparacion.estado, Reparacion.fecha_entrada,
                        Reparacion.precio, Reparacion.descripcion,
                        Cliente.nombre.label('cliente'), Cliente.telefono,
                        Cliente.email.label('cliente_email'),
                        Reparacion.estado_pago, Reparacion.fecha_pago,
                        Reparacion.metodo_pago,
                    ).join(Cliente, Cliente.id == Reparacion.cliente_id)
                    .where(Reparacion.codigo_publico == codigo)
                ).mappings().first()

            if not reparacion:
                error = "No se encontró ninguna reparación con ese código."

    return render_template("consulta.html", reparacion=reparacion, error=error,
                           codigo_prefill=codigo_get)


@bp.route("/mis-reparaciones", methods=["GET", "POST"])
@bp.route("/t/<slug>/mis-reparaciones", methods=["GET", "POST"])
@limiter.limit("30 per minute", methods=["POST"])  # H5: anti-abuso/enumeración
@csrf_protect
def mis_reparaciones(slug=None):
    """Panel publico: el cliente introduce su email y ve todas sus reparaciones."""
    # H5: mensaje genérico ÚNICO para "no hay resultados" — no revela si un email
    # es o no cliente (anti-enumeración). Sólo se muestran datos a quien acierta
    # un email con reparaciones (su propio dueño).
    _MSG_SIN_RESULTADOS = "No encontramos reparaciones asociadas a ese email."
    reparaciones_list = None
    cliente_nombre = None
    email_buscado = None
    error = None

    if request.method == "POST":
        email_buscado = request.form.get("email", "").strip().lower()
        if not email_buscado or '@' not in email_buscado:
            error = "Por favor, introduce un email valido."
        else:
            with get_session() as s:
                cliente = s.scalars(
                    select(Cliente).where(func.lower(Cliente.email) == email_buscado)
                ).first()

                if not cliente:
                    error = _MSG_SIN_RESULTADOS
                else:
                    cliente_nombre = cliente.nombre
                    reparaciones_list = s.execute(
                        select(
                            Reparacion.id, Reparacion.dispositivo,
                            Reparacion.descripcion, Reparacion.estado,
                            Reparacion.estado_pago, Reparacion.precio,
                            Reparacion.fecha_entrada, Reparacion.fecha_pago,
                            Reparacion.metodo_pago,
                        ).where(Reparacion.cliente_id == cliente.id)
                        .order_by(Reparacion.fecha_entrada.desc())
                    ).mappings().all()

                    if not reparaciones_list:
                        error = _MSG_SIN_RESULTADOS
                        cliente_nombre = None  # no revelar que el email es cliente
                        reparaciones_list = None

    return render_template("mis_reparaciones.html",
        reparaciones=reparaciones_list,
        cliente_nombre=cliente_nombre,
        email_buscado=email_buscado,
        error=error
    )


# =========================================
# SOLICITAR REPARACION (PUBLICO)
# =========================================
@bp.route("/solicitar-reparacion", methods=["GET", "POST"])
@bp.route("/t/<slug>/solicitar-reparacion", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])  # anti-spam del portal público
@csrf_protect
def solicitar_reparacion(slug=None):
    """Formulario publico para que clientes soliciten una reparacion."""
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip()
        dispositivo = request.form.get("dispositivo", "").strip()
        marca = request.form.get("marca", "").strip()
        modelo = request.form.get("modelo", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        urgencia = request.form.get("urgencia", "normal")
        fecha_preferida = request.form.get("fecha_preferida", "").strip()
        horario_preferido = request.form.get("horario_preferido", "").strip()

        # Validaciones
        if not nombre or len(nombre) < 2:
            flash("El nombre es obligatorio (minimo 2 caracteres).", "danger")
            return redirect(url_for("publico.solicitar_reparacion"))
        if not telefono or len(telefono) < 9:
            flash("El telefono es obligatorio (minimo 9 digitos).", "danger")
            return redirect(url_for("publico.solicitar_reparacion"))
        if not dispositivo:
            flash("Selecciona el tipo de dispositivo.", "danger")
            return redirect(url_for("publico.solicitar_reparacion"))
        if not descripcion or len(descripcion) < 10:
            flash("Describe el problema con al menos 10 caracteres.", "danger")
            return redirect(url_for("publico.solicitar_reparacion"))
        if urgencia not in ('normal', 'urgente'):
            urgencia = 'normal'

        with get_session() as s:
            s.add(SolicitudReparacion(
                nombre=nombre, telefono=telefono, email=email,
                dispositivo=dispositivo, marca=marca, modelo=modelo,
                descripcion=descripcion, urgencia=urgencia,
                fecha_preferida=fecha_preferida,
                horario_preferido=horario_preferido,
                estado='pendiente',
                fecha_solicitud=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ))
            s.commit()

        flash("Tu solicitud de reparacion ha sido enviada correctamente. Te contactaremos pronto.", "success")
        return redirect(url_for("publico.solicitar_reparacion"))

    return render_template("solicitar_reparacion.html")


@bp.route("/notificaciones/baja/<token>")
def baja_notificaciones(token):
    """Opt-out del cliente final de los avisos automáticos por email (B3).

    Enlace del pie de los emails de aviso. Sin login. El token va FIRMADO: nadie
    puede dar de baja a otro cliente manipulando el id. El UPDATE va acotado al
    (cliente, taller) DEL TOKEN — no a g.taller_id — y es Core/raw, así que el
    aislamiento lo impone el WHERE explícito (el token lo dicta, no la URL).
    """
    from itsdangerous import BadData

    try:
        datos = cargar_token_baja(token)
    except BadData:
        return render_template("baja_notificaciones.html", ok=False), 400

    cid, tid = datos.get("cid"), datos.get("tid")
    nombre = None
    with get_session() as s:
        s.execute(
            text("UPDATE clientes SET acepta_emails = 0 "
                 "WHERE id = :cid AND taller_id = :tid"),
            {"cid": cid, "tid": tid},
        )
        row = s.execute(
            text("SELECT nombre FROM clientes WHERE id = :cid AND taller_id = :tid"),
            {"cid": cid, "tid": tid},
        ).first()
        nombre = row[0] if row else None
        s.commit()
    logger.info('{"event": "notif_baja_cliente", "cliente_id": "%s", "taller_id": "%s"}'
                % (cid, tid))
    return render_template("baja_notificaciones.html", ok=True, nombre=nombre)
