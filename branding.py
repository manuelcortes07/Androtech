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
import os
import re

from flask import g
from sqlalchemy import text

from database import get_session

# Defaults legales/seguros. NO son marca de ningún taller.
IVA_DEFAULT = 0.21
MONEDA_DEFAULT = "EUR"
PLATAFORMA = "Kintsu"  # sólo para el discreto "Hecho con Kintsu"
ACCENT_DEFAULT = "#2F80FF"  # azul por defecto (= var --accent del CSS)

# Subcarpeta de los logos dentro de UPLOADS_DIR. El logo se sirve como estático
# (/static/uploads/logos/<file>), igual que las fotos de reparación.
_LOGO_SUBDIR = "logos"


def _uploads_dir() -> str:
    """Misma resolución que app.py (env UPLOADS_DIR → static/uploads del repo)."""
    base = os.environ.get("UPLOADS_DIR")
    if base:
        return base
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")


def _vacio() -> dict:
    return {
        "nombre": "", "direccion": "", "telefono": "", "telefono_wa": "",
        "email": "", "nif": "", "web": "",
        # logo_file: nombre de fichero guardado (o "").
        # logo_path: ruta de FICHERO absoluta (para embeber en el PDF).
        # logo_static: ruta relativa a /static (para url_for en plantillas web).
        "logo_file": "", "logo_path": "", "logo_static": "",
        "iva_rate": IVA_DEFAULT, "moneda": MONEDA_DEFAULT,
        "accent_color": "", "plataforma": PLATAFORMA,
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

    # Logo: en config guardamos sólo el NOMBRE de fichero (logo_file). De ahí
    # derivamos la ruta de fichero (PDF) y la ruta estática (web/email).
    logo_file = (cfg.get("logo_file") or "").strip()
    if logo_file:
        datos["logo_file"] = logo_file
        datos["logo_path"] = os.path.join(_uploads_dir(), _LOGO_SUBDIR, logo_file)
        datos["logo_static"] = f"uploads/{_LOGO_SUBDIR}/{logo_file}"

    try:
        datos["iva_rate"] = float(cfg.get("iva_rate", IVA_DEFAULT))
    except (TypeError, ValueError):
        pass
    datos["moneda"] = (cfg.get("moneda") or MONEDA_DEFAULT).strip() or MONEDA_DEFAULT
    # Color de acento por taller (Bloque 4): sólo si es un hex válido.
    accent = (cfg.get("accent_color") or "").strip()
    datos["accent_color"] = accent if _es_hex_color(accent) else ""
    return datos


def _es_hex_color(v: str) -> bool:
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", v or ""))


def logo_url_absoluto(marca: dict, base_url: str | None = None) -> str:
    """URL ABSOLUTA del logo para los emails (clientes de correo no resuelven
    rutas relativas). Usa `base_url` (request.host_url), si no APP_BASE_URL.
    Devuelve "" si el taller no tiene logo (degradar al nombre textual)."""
    static_rel = (marca or {}).get("logo_static")
    if not static_rel:
        return ""
    base = (base_url or os.environ.get("APP_BASE_URL") or "").rstrip("/")
    if not base:
        return ""  # sin host conocido no se puede construir absoluta → degrada
    return f"{base}/static/{static_rel}"
