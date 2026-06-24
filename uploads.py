"""Configuración y validación de subidas (refactor B1).

Carpetas de almacenamiento (fotos de reparación, firmas, logos de taller) y la
validación segura de imágenes (magic bytes — sin SVG —, límite por archivo). Se
extrae aquí para que app.py y los blueprints compartan una ÚNICA definición.

⚠️ Las carpetas se computan de la env var `UPLOADS_DIR` (en Railway, el volumen
persistente). Los handlers DEBEN leerlas por atributo de módulo en tiempo de
llamada (`uploads.LOGO_FOLDER`), no `from uploads import LOGO_FOLDER`: en tests,
`UPLOADS_DIR` apunta a un tmpdir antes de importar la app, así que estas rutas ya
quedan bajo el tmpdir (ningún test escribe en el `static/uploads/` real).
"""

from __future__ import annotations

import os

# Base de subidas: env UPLOADS_DIR o `static/uploads` del repo. DEBE quedar bajo
# `static/` para que `url_for('static', ...)` sirva fotos/firmas/logos.
_DEFAULT_UPLOADS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
UPLOADS_DIR = os.environ.get('UPLOADS_DIR') or _DEFAULT_UPLOADS

UPLOAD_FOLDER = os.path.join(UPLOADS_DIR, 'reparaciones')
SIGNATURES_FOLDER = os.path.join(UPLOADS_DIR, 'firmas')
LOGO_FOLDER = os.path.join(UPLOADS_DIR, 'logos')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SIGNATURES_FOLDER, exist_ok=True)
os.makedirs(LOGO_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB por archivo


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# H10: validación de CONTENIDO real por magic bytes (no sólo la extensión) +
# límite POR ARCHIVO. Sin dependencias externas. Nota: SVG NO está en la lista
# (no tiene magic byte fiable y es vector de XSS) → se rechaza.
def _sniff_image_type(head: bytes):
    """Devuelve 'jpeg'|'png'|'gif'|'webp' según la cabecera, o None."""
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def es_imagen_valida(storage) -> bool:
    """True si el FileStorage es una imagen REAL (magic bytes) y ≤ 5 MB."""
    try:
        stream = storage.stream
        pos = stream.tell()
        head = stream.read(12)
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(pos)
    except Exception:
        return False
    return _sniff_image_type(head) is not None and 0 < size <= MAX_CONTENT_LENGTH
