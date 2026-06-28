"""Blueprint de PLATAFORMA — superadmin de Kintsu.

Centro de mando del dueño del SaaS: ve y gestiona TODOS los talleres. Es el ÚNICO
lugar legítimamente cross-taller. Doble salvaguarda en CADA ruta:
  1. `@superadmin_requerido` — un admin de taller normal recibe 403.
  2. `sin_filtro_taller(motivo)` — escape EXPLÍCITO y AUDITADO del aislamiento
     multi-tenant, sólo alrededor de las consultas agregadas que lo necesitan
     (los conteos por taller de modelos con scope). `Taller` no lleva taller_id,
     así que listarlo no necesita el escape, pero se mantiene dentro por claridad.

Marca KINTSU (plataforma), no de un taller. El superadmin se designa SÓLO por CLI
(`scripts/set_superadmin.py`), nunca desde la web.
"""

from __future__ import annotations

import logging
import urllib.parse

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func, or_, select

from audit import registrar_auditoria
from auth import superadmin_requerido
from database import get_session
from models import Reparacion, Taller, Usuario
from pagination import paginar
from tenancy import sin_filtro_taller
from utils.security import csrf_protect

logger = logging.getLogger("androtech")

bp = Blueprint("plataforma", __name__)


@bp.route("/plataforma")
@superadmin_requerido
def panel():
    """Listado de TODOS los talleres con estado de suscripción y métricas baratas."""
    q = (request.args.get("q") or "").strip()
    with sin_filtro_taller("panel superadmin: listado de talleres"):
        with get_session() as s:
            base = select(Taller)
            if q:
                like = f"%{q}%"
                base = base.where(or_(
                    Taller.nombre.like(like),
                    Taller.email_contacto.like(like),
                    Taller.slug.like(like),
                ))
            total = s.scalar(select(func.count()).select_from(base.subquery()))
            pag = paginar(total)
            talleres = s.scalars(
                base.order_by(Taller.id).limit(pag.per_page).offset(pag.offset)
            ).all()
            # Conteos agregados por taller (cross-taller dentro del escape).
            rep_counts = dict(s.execute(
                select(Reparacion.taller_id, func.count(Reparacion.id))
                .group_by(Reparacion.taller_id)).all())
            user_counts = dict(s.execute(
                select(Usuario.taller_id, func.count(Usuario.id))
                .group_by(Usuario.taller_id)).all())
            ult_actividad = dict(s.execute(
                select(Reparacion.taller_id, func.max(Reparacion.fecha_entrada))
                .group_by(Reparacion.taller_id)).all())
            # Materializar a dicts simples (válidos tras cerrar la sesión).
            filas = [{
                "id": t.id, "nombre": t.nombre, "slug": t.slug,
                "email_contacto": t.email_contacto, "fecha_alta": t.fecha_alta,
                "estado": t.estado, "trial_fin": t.trial_fin,
                "n_reparaciones": rep_counts.get(t.id, 0),
                "n_usuarios": user_counts.get(t.id, 0),
                "ultima_actividad": ult_actividad.get(t.id),
            } for t in talleres]
    filters_query = urllib.parse.urlencode({"q": q}) if q else ""
    return render_template("plataforma_talleres.html", talleres=filas, pagina=pag,
                           q=q, filters_query=filters_query)


def _taller_simple(tid):
    """(id, nombre, estado) del taller, o None. Taller no lleva taller_id, así
    que no lo alcanza el filtro automático: el acceso es cross-taller por diseño."""
    with get_session() as s:
        row = s.execute(
            select(Taller.id, Taller.nombre, Taller.estado).where(Taller.id == tid)
        ).first()
    return row


@bp.route("/plataforma/talleres/<int:tid>/suspender", methods=["GET", "POST"])
@superadmin_requerido
@csrf_protect
def suspender(tid):
    """Suspende un taller (estado='suspendido'). GET = página de confirmación;
    POST = aplica. Reutiliza la PUERTA de suscripción: un taller suspendido queda
    bloqueado al entrar (sus datos se conservan, no se borran)."""
    row = _taller_simple(tid)
    if not row:
        flash("Taller no encontrado.", "danger")
        return redirect(url_for("plataforma.panel"))
    if request.method == "GET":
        return render_template("plataforma_suspender.html",
                               taller={"id": row[0], "nombre": row[1]})
    with get_session() as s:
        taller = s.get(Taller, tid)
        if taller:
            taller.estado = "suspendido"
            s.commit()
    registrar_auditoria("taller_suspendido", session.get("usuario"),
                        {"taller_id": tid, "nombre": row[1]}, taller_id=tid)
    flash(f"Taller «{row[1]}» suspendido. Sus datos se conservan.", "warning")
    return redirect(url_for("plataforma.panel"))


@bp.route("/plataforma/talleres/<int:tid>/reactivar", methods=["POST"])
@superadmin_requerido
@csrf_protect
def reactivar(tid):
    """Reactiva un taller suspendido (estado='activo'). Acción reversible y no
    destructiva → POST directo (sin página de confirmación)."""
    row = _taller_simple(tid)
    if not row:
        flash("Taller no encontrado.", "danger")
        return redirect(url_for("plataforma.panel"))
    with get_session() as s:
        taller = s.get(Taller, tid)
        if taller:
            taller.estado = "activo"
            s.commit()
    registrar_auditoria("taller_reactivado", session.get("usuario"),
                        {"taller_id": tid, "nombre": row[1]}, taller_id=tid)
    flash(f"Taller «{row[1]}» reactivado.", "success")
    return redirect(url_for("plataforma.panel"))
