"""Configuración por taller (B6): helpers get/set sobre TallerSetting.

Almacén clave→valor con scope de taller. El aislamiento es AUTOMÁTICO: las
consultas pasan por el filtro de `tenancy` (se acotan a `g.taller_id`) y los
INSERT reciben el `taller_id` por el auto-stamp. Por eso estos helpers NO
mencionan taller_id: operan sobre el taller activo de la petición.

Es la COSTURA para futuras preferencias (horarios, notificaciones, branding…):
una feature nueva guarda su ajuste con una clave, sin migrar el esquema.
"""

from __future__ import annotations

from sqlalchemy import select

from database import get_session
from models import TallerSetting


def get_setting(clave: str, default: str | None = None) -> str | None:
    """Valor de `clave` para el taller activo, o `default` si no existe."""
    with get_session() as s:
        row = s.scalars(select(TallerSetting).where(TallerSetting.clave == clave)).first()
        return row.valor if row else default


def set_setting(clave: str, valor: str) -> None:
    """Crea o actualiza `clave` para el taller activo (upsert por taller)."""
    with get_session() as s:
        row = s.scalars(select(TallerSetting).where(TallerSetting.clave == clave)).first()
        if row:
            row.valor = valor
        else:
            # taller_id lo sella el auto-stamp (before_flush) con el taller activo.
            s.add(TallerSetting(clave=clave, valor=valor))
        s.commit()


def all_settings() -> dict[str, str]:
    """Todos los ajustes del taller activo como dict."""
    with get_session() as s:
        rows = s.scalars(select(TallerSetting)).all()
        return {r.clave: r.valor for r in rows}
