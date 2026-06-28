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

from flask import Blueprint, render_template, request
from sqlalchemy import func, or_, select

from auth import superadmin_requerido
from database import get_session
from models import Reparacion, Taller, Usuario
from pagination import paginar
from tenancy import sin_filtro_taller

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
