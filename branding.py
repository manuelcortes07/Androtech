"""Branding por taller — el EMISOR de todo lo que ve el cliente final.

Plano (b) del rebranding: el escaparate público, los PDF (presupuesto/factura/
ticket/historial), los CSV y los emails al cliente deben llevar los datos del
TALLER activo (nombre, dirección, teléfono, email, NIF, logo, IVA), nunca una
constante hardcodeada y nunca la marca de la PLATAFORMA ("Kintsu").

`taller_branding()` lee el `Taller` por su id (el de la petición, `g.taller_id`,
o uno explícito) y degrada con elegancia: si falta un dato devuelve "" y si no
hay taller devuelve sólo los defaults legales (IVA 21 %, EUR). El nombre del
taller, si existe, SIEMPRE es el suyo.

No es una tabla con scope: `talleres` ES el tenant, así que un `SELECT ... WHERE
id = :t` por su propio id es seguro (no hay fuga: pedimos exactamente el taller
que toca). Se usa `SELECT *` para ser forward-compatible con columnas nuevas
(p. ej. `nif`) sin tener que tocar este helper en cada migración.
"""

from __future__ import annotations

import json
import re

from flask import g
from sqlalchemy import text

from database import get_session

# Defaults legales/seguros. NO son marca de ningún taller.
IVA_DEFAULT = 0.21
MONEDA_DEFAULT = "EUR"
PLATAFORMA = "Kintsu"  # sólo para el discreto "Hecho con Kintsu"


def _vacio() -> dict:
    return {
        "nombre": "", "direccion": "", "telefono": "", "telefono_wa": "",
        "email": "", "nif": "", "web": "", "logo_path": "",
        "iva_rate": IVA_DEFAULT, "moneda": MONEDA_DEFAULT,
        "plataforma": PLATAFORMA,
    }


def taller_branding(taller_id: int | None = None) -> dict:
    """Datos de marca del taller activo (o del `taller_id` dado) para documentos."""
    datos = _vacio()
    tid = taller_id if taller_id is not None else getattr(g, "taller_id", None)
    if not tid:
        return datos

    try:
        with get_session() as s:
            row = s.execute(
                text("SELECT * FROM talleres WHERE id = :t"), {"t": tid}
            ).mappings().first()
    except Exception:
        row = None
    if not row:
        return datos

    datos["nombre"] = (row.get("nombre") or "").strip()
    datos["direccion"] = (row.get("direccion") or "").strip()
    datos["telefono"] = (row.get("telefono") or "").strip()
    datos["telefono_wa"] = re.sub(r"\D", "", datos["telefono"])
    datos["email"] = (row.get("email_contacto") or "").strip()
    datos["nif"] = (row.get("nif") or "").strip()

    cfg = {}
    raw = row.get("config")
    if raw:
        try:
            cfg = json.loads(raw)
        except Exception:
            cfg = {}
    datos["web"] = (cfg.get("web") or "").strip()
    datos["logo_path"] = (cfg.get("logo_path") or "").strip()
    try:
        datos["iva_rate"] = float(cfg.get("iva_rate", IVA_DEFAULT))
    except (TypeError, ValueError):
        pass
    datos["moneda"] = (cfg.get("moneda") or MONEDA_DEFAULT).strip() or MONEDA_DEFAULT
    return datos
