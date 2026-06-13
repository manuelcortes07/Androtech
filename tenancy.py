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

Las consultas de resolución usan `exec_driver_sql` (SQL crudo) a propósito:
NO deben pasar por el filtro automático del ORM (Fase 2.3), porque resolver
"a qué taller pertenece este id/slug" precede a saber el taller.
"""

from __future__ import annotations

import re

from flask import g, request, session, abort

from database import get_engine

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
        row = conn.exec_driver_sql(
            "SELECT id, slug FROM talleres WHERE slug = ?", (slug,)
        ).first()
    return row


def _slug_por_taller_id(taller_id: int) -> str | None:
    with get_engine().connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT slug FROM talleres WHERE id = ?", (taller_id,)
        ).first()
    return row[0] if row else None


def _taller_de_reparacion(reparacion_id: str):
    """Devuelve el taller_id de una reparación por su id (PK global). SQL crudo."""
    try:
        rid = int(reparacion_id)
    except (TypeError, ValueError):
        return None
    with get_engine().connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT taller_id FROM reparaciones WHERE id = ?", (rid,)
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
