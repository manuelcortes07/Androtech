"""Extensiones Flask compartidas (refactor B1 — blueprints).

Se definen aquí, SIN la app, para que tanto `app.py` (la fábrica) como los
blueprints las importen sin ciclos. La app se enlaza en `create_app()` con
`limiter.init_app(app)`.

El backend del rate-limit es configurable por entorno (H9): RATELIMIT_STORAGE_URI
o REDIS_URL; si no, `memory://` (suficiente para desarrollo/tests). En producción
con varios workers, `memory://` NO se comparte entre procesos → define Redis.
"""

from __future__ import annotations

import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def _resolve_ratelimit_storage() -> str:
    return (
        os.environ.get("RATELIMIT_STORAGE_URI")
        or os.environ.get("REDIS_URL")
        or "memory://"
    )


_RATELIMIT_STORAGE = _resolve_ratelimit_storage()

# Limiter sin app: se enlaza con limiter.init_app(app) en create_app().
limiter = Limiter(key_func=get_remote_address, storage_uri=_RATELIMIT_STORAGE)
