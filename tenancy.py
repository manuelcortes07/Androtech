"""Resolución del taller activo (multi-tenancy, Fase 2.2).

`g.taller_id` es la ÚNICA fuente de verdad del taller de la petición. Se
resuelve en un `before_request` (`resolver_taller`) con esta prioridad:

1. Rutas de PLATAFORMA (health, static, docs legacy): no necesitan taller.
2. Path con slug explícito `/t/{slug}/...`: el taller sale del slug
   (404 si el slug no existe).
3. Usuario autenticado: el taller sale de la SESIÓN (`session['taller_id']`,
   fijado en el login). Las rutas internas no cambian de URL.
4. Legacy `/consulta?id=X` (QR ya impresos): el taller se resuelve desde el
   id de la reparación (PK global única). Decisión de producto: estos QR
   viven para siempre.
5. Resto de rutas legacy públicas sin slug (`/login`, `/mis-reparaciones`,
   `/solicitar-reparacion`, `/`): por defecto el taller 1 ("androtech").

Las consultas de resolución usan `Connection.execute(text(...))` (SQL crudo
sobre el Engine, NO sobre la Session) a propósito: NO deben pasar por el
filtro automático del ORM (Fase 2.3), porque resolver "a qué taller pertenece
este id/slug" precede a saber el taller. Usan parámetros con nombre
(`:slug`/`:id`) para ser agnósticas del motor (SQLite y Postgres) — los `?`
nativos sólo valen en SQLite (Fase 3a.3).
"""

from __future__ import annotations

import re
import logging
from contextlib import contextmanager
from contextvars import ContextVar

from flask import g, request, session, abort, has_request_context
from sqlalchemy import event, text
from sqlalchemy.orm import Session, with_loader_criteria

from database import get_engine

logger = logging.getLogger("androtech")

# Taller original (compat legacy): las rutas sin slug ni sesión caen aquí.
DEFAULT_TALLER_ID = 1
DEFAULT_TALLER_SLUG = "androtech"

# Prefijos de rutas de PLATAFORMA: no pertenecen a ningún taller y por tanto
# no consultan datos con scope. El resolver las salta (g.taller_id = None).
_PLATFORM_PREFIXES = (
    "/health",
    "/static",
    "/docs",        # /docs/<sub>/<file>  (legacy TFG, sirve ficheros)
    "/docs-view",   # /docs-view/<sub>/<file>
    "/admin/defensa",
    "/favicon",
    "/manifest.json",
    "/sw.js",
    "/stripe/webhook",  # el webhook resuelve el taller desde la metadata (Fase 2.4)
    "/saas/webhook",    # webhook de suscripción del SaaS (Fase 3b): plataforma
)

_SLUG_RE = re.compile(r"^/t/([^/]+)")


def es_ruta_plataforma(path: str) -> bool:
    """True si la ruta es de plataforma (no necesita taller)."""
    return any(path == p or path.startswith(p + "/") for p in _PLATFORM_PREFIXES) \
        or path.startswith("/static/")


def _extraer_slug(path: str) -> str | None:
    m = _SLUG_RE.match(path)
    return m.group(1) if m else None


def _taller_por_slug(slug: str):
    """Devuelve (id, slug) del taller con ese slug, o None. SQL crudo."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT id, slug FROM talleres WHERE slug = :slug"),
            {"slug": slug},
        ).first()
    return row


def _slug_por_taller_id(taller_id: int) -> str | None:
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT slug FROM talleres WHERE id = :id"),
            {"id": taller_id},
        ).first()
    return row[0] if row else None


def _taller_de_reparacion(reparacion_id: str):
    """Devuelve el taller_id de una reparación por su id (PK global). SQL crudo."""
    try:
        rid = int(reparacion_id)
    except (TypeError, ValueError):
        return None
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT taller_id FROM reparaciones WHERE id = :id"),
            {"id": rid},
        ).first()
    return row[0] if row else None


def resolver_taller() -> None:
    """before_request: fija g.taller_id y g.taller_slug según la prioridad documentada."""
    path = request.path
    g.taller_id = None
    g.taller_slug = None

    # 1. Plataforma: no necesita taller.
    if es_ruta_plataforma(path):
        return

    # 2. Slug explícito en el path: /t/{slug}/...
    slug = _extraer_slug(path)
    if slug is not None:
        taller = _taller_por_slug(slug)
        if taller is None:
            abort(404)
        g.taller_id = taller[0]
        g.taller_slug = taller[1]
        return

    # 3. Usuario autenticado: taller desde la sesión (rutas internas).
    if session.get("usuario") and session.get("taller_id"):
        g.taller_id = session["taller_id"]
        g.taller_slug = session.get("taller_slug")
        return

    # 4. Legacy /consulta?id=X (QR impresos): resolver taller desde el id.
    if path == "/consulta" and request.args.get("id"):
        tid = _taller_de_reparacion(request.args.get("id"))
        if tid:
            g.taller_id = tid
            g.taller_slug = _slug_por_taller_id(tid)
            return

    # 5. Resto de legacy público sin slug: taller 1 ("androtech").
    g.taller_id = DEFAULT_TALLER_ID
    g.taller_slug = DEFAULT_TALLER_SLUG


# ═══════════════════════════════════════════════════════════════════════
# FILTRO AUTOMÁTICO POR TALLER (Fase 2.3) — el núcleo de la REGLA DE ORO
# ═══════════════════════════════════════════════════════════════════════
# Toda consulta ORM sobre un modelo con scope se filtra automáticamente por
# el taller activo (g.taller_id). Los INSERT reciben taller_id automáticamente.
# El único modo de ver varios talleres es el escape EXPLÍCITO sin_filtro_taller().

from models import (  # noqa: E402  (import tardío: evita ciclos en el arranque)
    Usuario, Cliente, Reparacion, FotoReparacion, NotaReparacion,
    PiezaReparacion, InventarioPieza, SolicitudReparacion, RepairHistorial,
    AuditLog,
)

# Los 10 modelos con columna taller_id (9 de scope NOT NULL + audit_log nullable).
_MODELOS_SCOPED = (
    Usuario, Cliente, Reparacion, FotoReparacion, NotaReparacion,
    PiezaReparacion, InventarioPieza, SolicitudReparacion, RepairHistorial,
    AuditLog,
)

# Escape explícito de plataforma (context-var, seguro entre hilos/peticiones).
_escape_filtro: ContextVar[bool] = ContextVar("sin_filtro_taller", default=False)


def _taller_para_filtrar():
    """taller_id por el que filtrar/sellar, o None si NO se debe filtrar.

    None (sin filtro) SOLO en estos casos legítimos:
      - escape explícito sin_filtro_taller() (plataforma, auditado),
      - fuera de un request HTTP (arranque, migración, scripts: código de
        confianza con acceso total),
      - rutas de plataforma (g.taller_id es None).
    En un request normal a una ruta con scope, g.taller_id SIEMPRE está fijado
    (el resolver pone taller 1 por defecto en el peor caso), así que el filtro
    SIEMPRE se aplica. Nunca hay fuga "por olvido".
    """
    if _escape_filtro.get():
        return None
    if not has_request_context():
        return None
    return getattr(g, "taller_id", None)


@event.listens_for(Session, "do_orm_execute")
def _filtrar_por_taller(execute_state):
    """Inyecta WHERE taller_id = :tid en toda SELECT ORM sobre modelos con scope."""
    if not execute_state.is_select:
        return
    tid = _taller_para_filtrar()
    if tid is None:
        return
    execute_state.statement = execute_state.statement.options(
        *[
            with_loader_criteria(
                modelo,
                modelo.taller_id == tid,
                include_aliases=True,
            )
            for modelo in _MODELOS_SCOPED
        ]
    )


@event.listens_for(Session, "before_flush")
def _sellar_taller_en_insert(session_, flush_context, instances):
    """Asigna taller_id automáticamente a los objetos nuevos con scope.

    Así ningún handler tiene que acordarse de poner taller_id en un INSERT.
    Respeta un taller_id ya fijado explícitamente (p. ej. seeds de tests).
    """
    tid = _taller_para_filtrar()
    if tid is None:
        return
    for obj in session_.new:
        if isinstance(obj, _MODELOS_SCOPED) and getattr(obj, "taller_id", None) is None:
            obj.taller_id = tid


@contextmanager
def sin_filtro_taller(motivo: str):
    """Escape EXPLÍCITO del filtro de taller, para operaciones de plataforma.

    Dentro del `with`, las consultas ORM ven TODOS los talleres. Es el único
    mecanismo autorizado para saltarse la regla de oro, y queda registrado en
    auditoría (taller_id NULL = evento de plataforma) y en el log.

    Uso:
        with sin_filtro_taller("listado de talleres del superadmin"):
            todos = s.scalars(select(Reparacion)).all()
    """
    from audit import registrar_auditoria  # import tardío: evita ciclo con app
    usuario = session.get("usuario") if has_request_context() else "sistema"
    token = _escape_filtro.set(True)
    try:
        logger.warning('{"event": "sin_filtro_taller", "motivo": %r, "usuario": %r}'
                       % (motivo, usuario))
        registrar_auditoria("sin_filtro_taller", usuario, {"motivo": motivo})
        yield
    finally:
        _escape_filtro.reset(token)
