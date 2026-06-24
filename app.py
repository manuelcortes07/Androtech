import json
import logging
import os
import secrets
import socket
import urllib.parse
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

# Cargar variables de entorno desde .env
load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# Timeout global de sockets — CRITICO para Railway.
# Sin esto, smtplib (y cualquier otra libreria de red que use sockets por defecto)
# puede quedarse colgada indefinidamente si el servidor remoto no responde.
# Esto provoca que el worker de gunicorn se cuelgue -> Railway devuelve 502 Bad
# Gateway. 20s es suficiente para Gmail SMTP, Stripe API y cualquier request
# razonable; si algo tarda mas, algo va muy mal.
# ──────────────────────────────────────────────────────────────────────────────
socket.setdefaulttimeout(20)

try:
    import stripe
except ImportError:
    stripe = None

# Esenciales de cuenta (B3): tokens firmados de reset/verificación.

# Capa de acceso a datos: SQLAlchemy (Fase 1 SaaS completada — todo el
# proyecto usa get_session()/select(); sqlite3 directo eliminado).
from sqlalchemy import select, text
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

# Suscripción del SaaS (Fase 3b) — flujo Stripe SEPARADO del de reparaciones.
import saas_billing
import tokens as account_tokens
from alerts import calcular_alertas_reparacion
from audit import crear_tabla_auditoria, obtener_auditoria_reciente, registrar_auditoria
from auth import (
    init_permisos_db,
    login_required,
    obtener_permisos_usuario,
    permiso_requerido,
    tiene_permiso,
)

# local modules (split responsibilities)
from branding import taller_branding
from database import get_engine, get_session, insert_or_ignore, is_postgres
from historial import registrar_cambio_estado, validar_transicion
from models import (
    Cliente,
    FotoReparacion,
    InventarioPieza,
    NotaReparacion,
    PiezaReparacion,
    RepairHistorial,
    Reparacion,
    StripeEvento,
)

# Paginación clásica numerada (B5).
from pagination import paginar
from utils.pdf_generator import generar_presupuesto_pdf
from utils.security import (
    csrf_protect,
    email_valido,
    ensure_csrf_token,
    inject_csrf_token,
    validar_contraseña,
    validar_precio,
    validate_csrf,
)

app = Flask(__name__)
# Trust Railway / Nginx reverse-proxy headers so request.host_url returns https://
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


def create_app():
    """Punto de entrada de fábrica (refactor B1, en curso).

    Hoy devuelve la app-singleton ya configurada a nivel de módulo (toda la
    configuración, extensiones, hooks y rutas se montan al importar este módulo).
    A medida que las rutas migran a blueprints en `blueprints/`, la configuración
    se irá moviendo aquí dentro. `gunicorn app:app` y `app:create_app()` son
    ambos válidos. Permite además crear instancias limpias en tests si hiciera
    falta sin reimportar el módulo.
    """
    return app

# Entorno de ejecución: 'production' en Railway, 'development' en local.
APP_ENV = os.environ.get('APP_ENV', 'development').strip().lower()
IS_PRODUCTION = APP_ENV == 'production'

# SECRET_KEY: en producción es OBLIGATORIA. Sin ella las sesiones/CSRF no son
# seguras y se invalidarían en cada reinicio o worker de gunicorn. Falla
# RUIDOSAMENTE si falta en producción; en local cae a un aleatorio para no
# estorbar el desarrollo.
_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    if IS_PRODUCTION:
        raise RuntimeError(
            "SECRET_KEY no está definida y APP_ENV=production. Define SECRET_KEY "
            "en las variables de entorno antes de arrancar en producción."
        )
    _secret_key = secrets.token_urlsafe(32)  # solo desarrollo local
app.secret_key = _secret_key

# Endurecimiento de cookies de sesión. SECURE (solo HTTPS) únicamente en
# producción; en local sobre http sigue funcionando porque SECURE=False.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_PRODUCTION,
)

# Rate limiter (protección contra fuerza bruta). Definido en extensions.py (sin
# app) y enlazado aquí. Re-exportamos los helpers para compatibilidad con los
# tests, que referencian app._resolve_ratelimit_storage / app._RATELIMIT_STORAGE.
# _RATELIMIT_STORAGE/_resolve_ratelimit_storage se re-exportan para los tests.
from extensions import (  # noqa: E402, F401
    _RATELIMIT_STORAGE,
    _resolve_ratelimit_storage,
    limiter,
)

limiter.init_app(app)
# Configure session expiration
app.permanent_session_lifetime = timedelta(hours=6)  # ajustable según política

# Ensure sessions are permanent by default + nonce CSP por petición
@app.before_request
def make_session_permanent():
    session.permanent = True
    # Nonce único por request para la CSP (scripts/estilos inline con nonce).
    g.csp_nonce = secrets.token_urlsafe(16)


@app.context_processor
def inject_csp_nonce():
    # Disponible en todas las plantillas como {{ csp_nonce }}.
    return {"csp_nonce": getattr(g, "csp_nonce", "")}

@app.errorhandler(429)
def ratelimit_handler(e):
    flash("Demasiados intentos. Espera un minuto antes de volver a intentarlo.", "danger")
    return redirect(url_for("auth.login"))

# Content-Security-Policy ENDURECIDA con nonce por petición (sin 'unsafe-inline').
# - Todo <script>/<style> inline de las plantillas lleva nonce="{{ csp_nonce }}".
#   No quedan atributos style="" ni handlers on*= en el HTML (movidos a CSS/JS).
# - Allowlist de hosts EXTERNOS realmente usados:
#     · scripts: jsdelivr (bootstrap, chart.js, fullcalendar, signature_pad)
#     · estilos: jsdelivr (bootstrap/icons) + fonts.googleapis.com (Google Fonts)
#     · fuentes: fonts.gstatic.com (ficheros) + jsdelivr (bootstrap-icons) + data:
# - Ninguna librería requiere 'unsafe-eval'. No hay fetch externos → connect 'self'.
def _build_csp(nonce: str) -> str:
    n = f"'nonce-{nonce}'"
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' {n} https://cdn.jsdelivr.net",
        f"style-src 'self' {n} https://cdn.jsdelivr.net https://fonts.googleapis.com",
        "img-src 'self' data: https:",
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net data:",
        "connect-src 'self'",
        "frame-ancestors 'self'",
        "base-uri 'self'",
        "form-action 'self'",
    ])


@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = _build_csp(getattr(g, 'csp_nonce', ''))
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    # HSTS sólo en producción (HTTPS). Los navegadores lo ignoran sobre http,
    # así que no estorba en local, pero lo limitamos a prod por higiene.
    if IS_PRODUCTION:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# -----------------------------
# Structured/JSON logger
# -----------------------------
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)


logger = logging.getLogger("androtech")
if not logger.handlers:
    # Stdout handler
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    # Archivo rotativo (max 5MB, 3 backups)
    from logging.handlers import RotatingFileHandler
    os.makedirs('logs', exist_ok=True)
    file_handler = RotatingFileHandler(
        'logs/androtech.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)

logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO').upper())

# ── Sentry (observabilidad de errores) — COSTURA, APAGADA por defecto ────────
# Sin SENTRY_DSN no hace nada y NO requiere la dependencia instalada. Si se
# define SENTRY_DSN y `sentry-sdk` está disponible, se inicializa. Pensado para
# activarlo en producción sin tocar código (sólo la env var + la dependencia).
_sentry_dsn = os.environ.get('SENTRY_DSN', '').strip()
if _sentry_dsn:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=_sentry_dsn,
                        environment=os.environ.get('APP_ENV', 'development'),
                        traces_sample_rate=0.0)
        logger.info('{"event": "sentry_inicializado"}')
    except Exception as _e:  # pragma: no cover (depende de dep externa)
        logger.warning('SENTRY_DSN definido pero no se pudo inicializar Sentry '
                       '(¿falta sentry-sdk?): %s', _e)

# Stripe configuration (use environment variables in production)
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

# Helper to mask keys for logging (never print full secret in logs)
def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return key
    return key[:4] + '...' + key[-4:]

# Configure Stripe API key if provided
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
else:
    logger.warning(
        "Stripe secret key not found in environment; payments will be disabled. "
        "Set STRIPE_SECRET_KEY to your sk_test_... value."
    )

# if the key is set but looks suspicious, log a warning too
if STRIPE_SECRET_KEY and not STRIPE_SECRET_KEY.startswith('sk_'):
    logger.warning(
        "Stripe secret key has unexpected format: %s",
        _mask_key(STRIPE_SECRET_KEY)
    )

# ─────────────────────────────────────────────────────────────────────
# Inicialización del esquema al arrancar — RAMIFICADA POR DIALECTO (Fase 3a)
# ─────────────────────────────────────────────────────────────────────
import models as _models  # noqa: F401  (registra todos los modelos en Base.metadata)
from database import Base as _Base
from migrations import (
    aplicar_migracion_multitenant,
    asegurar_codigo_publico,
    asegurar_es_superadmin,
    asegurar_taller_1,
    asegurar_taller_nif,
    crear_esquema_sqlite_defensivo,
    normalizar_taller_demo,
)

if is_postgres():
    # PostgreSQL: esquema FINAL directo desde los modelos (pincho F). Crea
    # TODAS las tablas con taller_id, UNIQUE(taller_id, usuario), FKs, índices
    # y ON DELETE CASCADE. NO se usa el rebuild 12-step (es SQLite-only).
    _Base.metadata.create_all(get_engine())
    init_permisos_db()
    asegurar_taller_1()
else:
    # SQLite: camino de siempre (DDL defensivo byte-idéntico + migración
    # 12-step in-place para BD existentes con esquema viejo).
    crear_tabla_auditoria()
    crear_esquema_sqlite_defensivo()
    init_permisos_db()
    aplicar_migracion_multitenant()

# H3: código público no adivinable para el portal /consulta (ambos motores).
asegurar_codigo_publico()
# H1: flag de superadmin de plataforma (sólo él edita roles globales).
asegurar_es_superadmin()
# Rebranding: NIF/CIF fiscal del taller (emisor de los documentos).
asegurar_taller_nif()
# Rebranding: normaliza el taller demo (id 1) si una BD existente sigue con la
# marca vieja (AndroTech/Huelva) → datos demo genéricos (idempotente).
normalizar_taller_demo()

# Configuración de subida de fotos/firmas/logos: extraída a uploads.py (B1).
# Las carpetas se leen vía `uploads.UPLOAD_FOLDER` (atributo de módulo) en
# tiempo de llamada; los validadores y el límite por-archivo se importan.
import uploads  # noqa: E402
from uploads import (  # noqa: E402, F401
    ALLOWED_EXTENSIONS,
    MAX_CONTENT_LENGTH,
    allowed_file,
    es_imagen_valida,
)

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB total por request

# ──────────────────────────────────────────────────────────────────────────────
# Flask-Mail configuration
# ──────────────────────────────────────────────────────────────────────────────
# IMPORTANTE: Para Gmail es OBLIGATORIO usar una "App Password" (contraseña de
# aplicación) de 16 caracteres, NO la contraseña normal de la cuenta.
# Se genera en: https://myaccount.google.com/apppasswords (requiere 2FA activo).
# Ademas, Gmail exige que el remitente (From) coincida con el usuario autenticado;
# por eso el default sender cae a MAIL_USERNAME si no se especifica otro.
# ──────────────────────────────────────────────────────────────────────────────
app.config['MAIL_SERVER']    = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT']      = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS']   = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL']   = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME']  = os.environ.get('MAIL_USERNAME', '')
# Normalizamos la password: Google muestra la App Password con espacios cada 4
# caracteres por legibilidad, pero SMTP exige los 16 chars sin espacios.
_raw_mail_pwd = os.environ.get('MAIL_PASSWORD', '') or ''
app.config['MAIL_PASSWORD']  = _raw_mail_pwd.replace(' ', '').strip()
# Si no se define MAIL_DEFAULT_SENDER, usamos el propio MAIL_USERNAME (único
# remitente que Gmail acepta sin rebote).
app.config['MAIL_DEFAULT_SENDER'] = (
    os.environ.get('MAIL_DEFAULT_SENDER')
    or app.config['MAIL_USERNAME']
    or 'noreply@androtech.local'
)
app.config['MAIL_DEFAULT_CHARSET']      = 'utf-8'
app.config['MAIL_DEFAULT_CONTENT_TYPE'] = 'text/html'
app.config['MAIL_SUPPRESS_SEND']        = False

# Flag interno: indica si el email está correctamente configurado.
# Lo consume /admin/sistema y /admin/test-email.
MAIL_CONFIGURED = bool(
    app.config['MAIL_USERNAME']
    and app.config['MAIL_PASSWORD']
    and len(app.config['MAIL_PASSWORD']) >= 12  # App Passwords = 16 chars
)

# Servicios compartidos (refactor B1): instancias únicas en services.py.
# `email_service` lee la config SMTP de current_app en cada envío, así que no
# necesita la app para construirse. `notificador` (B6) es la costura única de
# envío (email hoy; SMS/WhatsApp futuro) sobre ese email_service.
# email_service se re-exporta para los tests (parchean app.email_service).
from services import email_service, notificador  # noqa: E402, F401

# register CSRF helpers from utils/security
app.before_request(ensure_csrf_token)
app.context_processor(inject_csrf_token)

# Multi-tenancy (Fase 2.2): resolver el taller activo (g.taller_id) en cada
# petición. Debe correr antes de cualquier handler que consulte datos con scope.
from tenancy import es_ruta_plataforma, resolver_taller

app.before_request(resolver_taller)

# Puerta de acceso por suscripción (Fase 3b.3): tras resolver el taller,
# bloquea el acceso INTERNO de un taller cuya suscripción no está activa.
# Bloquear NUNCA borra datos: solo corta el acceso. El portal público (clientes
# finales) NO pasa por aquí (sólo actúa sobre usuarios con sesión).
_GATE_EXENTAS = frozenset({
    # Auth y alta
    "auth.login", "auth.logout", "signup",
    # Facturación: un taller bloqueado DEBE poder llegar a pagar/gestionar
    "suscripcion", "suscripcion_portal", "suscripcion_bloqueado",
    # Webhooks (sin sesión, pero exentos por claridad)
    "saas_webhook", "stripe_webhook",
    "static", "health",
    # Portal público del taller: SIEMPRE visible (decisión de producto) — un
    # taller bloqueado no perjudica a sus clientes finales.
    "publico.consulta", "publico.mis_reparaciones", "publico.solicitar_reparacion",
    "publico_pagar", "pago_exito",
})


def puerta_suscripcion():
    """before_request: corta el acceso interno si la suscripción no está activa."""
    # Sólo afecta a usuarios autenticados (staff del taller). Los clientes
    # finales del portal público no tienen sesión → nunca se bloquean.
    if not session.get("usuario"):
        return
    if request.endpoint in _GATE_EXENTAS:
        return
    if es_ruta_plataforma(request.path):
        return
    tid = session.get("taller_id")
    if not tid:
        return
    with get_session() as s:
        row = s.execute(
            text("SELECT estado, trial_fin FROM talleres WHERE id = :t"),
            {"t": tid},
        ).first()
    if not row:
        return
    if saas_billing.acceso_bloqueado(row[0], row[1]):
        # No se toca ningún dato: sólo se redirige a la página de bloqueo.
        return redirect(url_for("suscripcion_bloqueado"))


app.before_request(puerta_suscripcion)

# Exponer el taller activo a las plantillas (para construir URLs /t/{slug}/...).
@app.context_processor
def inject_taller():
    # `marca` = datos del taller activo para el escaparate público y los pies
    # (plano (b) del rebranding). Degrada a defaults si no hay taller resuelto.
    from branding import taller_branding
    return dict(taller_slug=getattr(g, 'taller_slug', None),
                taller_id=getattr(g, 'taller_id', None),
                marca=taller_branding())

# REGISTRAR FILTRO PERSONALIZADO PARA JINJA2
@app.template_filter('strftime')
def strftime_filter(date_str, format_str='%d/%m/%Y'):
    """Filtro para formatear fechas en Jinja2. Si date_str es vacío, retorna hoy"""
    if not date_str or date_str == '':
        return datetime.now().strftime(format_str)
    if isinstance(date_str, str):
        # Intentar parsear la fecha
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        except Exception:
            return date_str
    else:
        date_obj = date_str
    return date_obj.strftime(format_str)


# build_reparaciones_filters + _ultimas_actualizaciones: extraídos a
# query_helpers.py (refactor B1). Re-exportados para los tests.
from query_helpers import (  # noqa: E402, F401
    _ultimas_actualizaciones,
    build_reparaciones_filters,
)


# ==============================
# Endpoint: Export reparaciones (filtrado)
# ==============================
@app.route('/export/reparaciones', methods=['GET'])
@login_required
def export_reparaciones():
    # Permitir admin o recepcionista
    rol = session.get('rol')
    if rol not in ('admin', 'recepcionista'):
        flash('No tienes permisos para exportar datos.', 'danger')
        return redirect(url_for('reparaciones'))

    where, params = build_reparaciones_filters(request.args)

    # Fase 2.4: filtro MANUAL de taller en el raw SQL del export filtrado.
    from sqlalchemy import text as _text
    params["tid"] = g.taller_id
    query = (
        "SELECT reparaciones.id, clientes.nombre as cliente, clientes.telefono, "
        "reparaciones.dispositivo, reparaciones.estado, reparaciones.estado_pago, "
        "reparaciones.precio, reparaciones.fecha_entrada, reparaciones.fecha_pago as fecha_finalizacion "
        "FROM reparaciones JOIN clientes ON clientes.id = reparaciones.cliente_id "
        f"WHERE reparaciones.taller_id = :tid AND ({where}) ORDER BY reparaciones.id DESC"
    )
    with get_session() as s:
        rows = s.execute(_text(query), params).mappings().all()

    # ── Estadísticas ─────────────────────────────────────────────────────────
    total            = len(rows)
    total_facturado  = sum(r['precio'] or 0 for r in rows)
    total_pagado     = sum(r['precio'] or 0 for r in rows if r['estado_pago'] == 'Pagado')
    total_pendiente  = total_facturado - total_pagado
    n_pendiente      = sum(1 for r in rows if r['estado'] == 'Pendiente')
    n_en_proceso     = sum(1 for r in rows if r['estado'] == 'En proceso')
    n_terminado      = sum(1 for r in rows if r['estado'] == 'Terminado')
    n_entregado      = sum(1 for r in rows if r['estado'] == 'Entregado')

    si = StringIO()
    w  = csv.writer(si, delimiter=';')

    # ── Cabecera corporativa ──────────────────────────────────────────────────
    _csv_empresa_header(w, 'INFORME FILTRADO DE REPARACIONES')

    # ── Resumen ejecutivo ─────────────────────────────────────────────────────
    w.writerow(['--- RESUMEN ---'])
    w.writerow(['Total reparaciones', total])
    w.writerow(['Total facturado',    _fmt_precio_csv(total_facturado)])
    w.writerow(['Total cobrado',      _fmt_precio_csv(total_pagado)])
    w.writerow(['Pendiente de cobro', _fmt_precio_csv(total_pendiente)])
    w.writerow([])
    w.writerow(['Estado', 'Cantidad'])
    w.writerow(['Pendiente',   n_pendiente])
    w.writerow(['En proceso',  n_en_proceso])
    w.writerow(['Terminado',   n_terminado])
    w.writerow(['Entregado',   n_entregado])
    w.writerow([])

    # ── Datos ─────────────────────────────────────────────────────────────────
    w.writerow(['--- DETALLE DE REPARACIONES ---'])
    w.writerow([
        'N. Reparacion', 'Cliente', 'Telefono', 'Dispositivo',
        'Estado', 'Estado Pago', 'Precio',
        'Fecha Entrada', 'Fecha Finalizacion', 'Dias en Taller', 'Alertas',
    ])

    for r in rows:
        rdict = dict(r)
        fecha_entrada = rdict.get('fecha_entrada')
        fecha_fin     = rdict.get('fecha_finalizacion')

        # calcular dias en taller (usando fechas crudas)
        dias = ''
        try:
            if fecha_entrada:
                d_ent = datetime.strptime(str(fecha_entrada)[:10], '%Y-%m-%d')
                d_fin = datetime.strptime(str(fecha_fin)[:10], '%Y-%m-%d') if fecha_fin else datetime.now()
                dias  = (d_fin - d_ent).days
        except Exception:
            dias = ''

        # alertas en texto plano
        alertas_txt = ''
        try:
            alert_info = calcular_alertas_reparacion(rdict)
            if alert_info and alert_info.get('tiene_alertas'):
                alertas_txt = ' | '.join(a['mensaje'] for a in alert_info['alertas'])
        except Exception:
            alertas_txt = ''

        w.writerow([
            rdict.get('id'),
            rdict.get('cliente')   or 'Sin asignar',
            rdict.get('telefono')  or '',
            rdict.get('dispositivo'),
            rdict.get('estado'),
            rdict.get('estado_pago'),
            _fmt_precio_csv(rdict.get('precio')),
            _fmt_fecha_csv(fecha_entrada),
            _fmt_fecha_csv(fecha_fin),
            dias,
            alertas_txt,
        ])

    # ── Pie ───────────────────────────────────────────────────────────────────
    w.writerow([])
    w.writerow([_SEP_CSV])
    _csv_pie(w)
    w.writerow([_SEP_CSV])

    output = BytesIO()
    output.write(si.getvalue().encode('utf-8-sig'))
    output.seek(0)
    return send_file(output, mimetype='text/csv', as_attachment=True,
                     download_name=f'{_csv_filename_prefix()}_Reparaciones_Filtro_{datetime.now().strftime("%Y%m%d_%H%M")}.csv')



# CSRF PROTECCIÓN (simple token en sesión)
@app.before_request
def ensure_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(16)

@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=session.get('csrf_token'))

@app.context_processor
def inject_permisos():
    return dict(tiene_permiso=tiene_permiso)


# `validate_csrf` se importa de utils.security (con cabecera X-CSRFToken +
# comparación constante). La definición local duplicada se eliminó (H2/H11).

# CSRF POR DEFECTO (H2): todo POST se valida automáticamente, salvo exenciones
# explícitas. Así ninguna ruta puede "olvidarse" del token. Los webhooks van
# por firma de Stripe (no por CSRF) y quedan exentos. El @csrf_protect de cada
# ruta sigue presente como defensa local explícita (redundante pero deliberado).
_CSRF_EXENTAS = frozenset({"stripe_webhook", "saas_webhook"})


@app.before_request
def enforce_csrf():
    if request.method != "POST":
        return
    if request.endpoint in _CSRF_EXENTAS:
        return
    if validate_csrf():
        return
    # Rechazo: JSON/cabecera → 403; formulario → vuelve atrás sin aplicar nada.
    if request.is_json or request.headers.get("X-CSRFToken"):
        return jsonify({"error": "Token CSRF inválido"}), 403
    return redirect(request.referrer or request.url)


# Authentication decorators (`login_required`, `role_required`) are
# now located in auth.py; they are imported above.
# History recording logic has been delegated to historial.py;
# the helper ``registrar_cambio_estado`` is imported at the top of
# this file for use in the routes where state changes occur.

# Alert calculation logic now lives in alerts.py; the
# ``calcular_alertas_reparacion`` function is imported above.
# =========================================
# 🔸 AUTENTICACIÓN
# =========================================

# Las rutas de autenticación viven ahora en blueprints/auth.py (refactor B1).
from blueprints.auth import bp as auth_bp  # noqa: E402

app.register_blueprint(auth_bp)


@app.context_processor
def inject_email_verificacion():
    """Expone a las plantillas si el taller activo tiene el email pendiente de
    verificar (para el aviso no bloqueante en base.html)."""
    if not session.get("usuario") or not session.get("taller_id"):
        return {}
    try:
        with get_session() as s:
            row = s.execute(
                text("SELECT email_verificado FROM talleres WHERE id = :t"),
                {"t": session["taller_id"]},
            ).first()
        return {"email_pendiente_verificar": bool(row and not row[0])}
    except Exception:
        return {}


# =========================================
# 🔸 PERFIL: GESTIÓN DE CREDENCIALES (B3.3)
# =========================================
# Dominio cuenta/perfil: ahora en blueprints/cuenta.py (refactor B1).
from blueprints.cuenta import bp as cuenta_bp  # noqa: E402

app.register_blueprint(cuenta_bp)


# =========================================
# 🔸 SUSCRIPCIÓN DEL SaaS (Fase 3b) — registro self-service + facturación
# =========================================
# ⚠️ Flujo SEPARADO del pago de reparaciones (publico_pagar + /stripe/webhook).
# Aquí YO cobro a los talleres (suscripción 24,99 €/mes, trial 14 días con
# tarjeta requerida). Claves/price/webhook propios (módulo saas_billing).
import re as _re


def _slugify(nombre: str) -> str:
    """Convierte el nombre del taller en un slug URL-safe."""
    base = nombre.strip().lower()
    base = base.replace("ñ", "n")
    # quita acentos básicos
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        base = base.replace(a, b)
    base = _re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base or "taller"


def _slug_unico(base: str) -> str:
    """Devuelve un slug que no colisiona con otro taller (base, base-2, …)."""
    with get_session() as s:
        existentes = set(s.execute(text("SELECT slug FROM talleres")).scalars().all())
    if base not in existentes:
        return base
    i = 2
    while f"{base}-{i}" in existentes:
        i += 1
    return f"{base}-{i}"


# _email_valido se trasladó a utils.security.email_valido (B1); alias local.
_email_valido = email_valido


def _sval(obj, key):
    """Lee un campo de un objeto Stripe (atributo) o de un dict (mock/test)."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


@app.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
@csrf_protect
def signup():
    """Alta self-service de un taller nuevo: crea Taller + admin + Stripe
    Customer y arranca un Checkout de suscripción (trial 14 días, tarjeta
    requerida). Transacción: si Stripe falla, NO quedan talleres a medias.
    """
    if request.method == "GET":
        return render_template("signup.html")

    nombre = request.form.get("nombre_taller", "").strip()
    email = request.form.get("email", "").strip().lower()
    admin_user = request.form.get("usuario", "").strip()
    password = request.form.get("password", "")

    errores = []
    if not nombre:
        errores.append("El nombre del taller es obligatorio.")
    if not _email_valido(email):
        errores.append("Introduce un email válido.")
    if not admin_user:
        errores.append("El usuario administrador es obligatorio.")
    _ok_pwd, _msg_pwd = validar_contraseña(password)
    if not _ok_pwd:
        errores.append(_msg_pwd)
    if errores:
        for e in errores:
            flash(e, "danger")
        return render_template("signup.html", nombre=nombre, email=email,
                               usuario=admin_user), 400

    # Email único a nivel PLATAFORMA (talleres no lleva scope de taller).
    with get_session() as s:
        ya = s.execute(
            text("SELECT 1 FROM talleres WHERE lower(email_contacto) = :e"),
            {"e": email},
        ).first()
    if ya:
        flash("Ya existe una cuenta con ese email.", "danger")
        return render_template("signup.html", nombre=nombre, usuario=admin_user), 400

    slug = _slug_unico(_slugify(nombre))

    # 1) Stripe Customer PRIMERO (si falla, no se crea nada en BD).
    customer_id = None
    if saas_billing.is_configured():
        try:
            cust = saas_billing.crear_customer(email, nombre)
            customer_id = _sval(cust, "id")
        except Exception as e:
            logger.error(json.dumps({"event": "signup_stripe_customer_error",
                                     "error": str(e)}, ensure_ascii=False))
            flash("No se pudo iniciar el alta con la pasarela de pago. "
                  "Inténtalo de nuevo en unos minutos.", "danger")
            return render_template("signup.html", nombre=nombre, email=email,
                                   usuario=admin_user), 502

    # 2) Taller + admin + (opcional) Checkout en UNA transacción. Si el Checkout
    #    falla, el `with` sale por excepción SIN commit → rollback total.
    trial_fin = saas_billing.trial_fin_str()
    checkout_url = None
    nuevo_tid = None
    try:
        with get_session() as s:
            nuevo_tid = s.execute(
                text("""INSERT INTO talleres
                        (nombre, slug, email_contacto, fecha_alta, estado, plan,
                         stripe_customer_id, trial_fin)
                        VALUES (:n, :sl, :e, :fa, 'trial', 'basico', :cust, :tf)
                        RETURNING id"""),
                {"n": nombre, "sl": slug, "e": email,
                 "fa": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "cust": customer_id, "tf": trial_fin},
            ).scalar()
            s.execute(
                text('INSERT INTO usuarios (taller_id, usuario, "contraseña", rol) '
                     'VALUES (:tid, :u, :p, \'admin\')'),
                {"tid": nuevo_tid, "u": admin_user,
                 "p": generate_password_hash(password)},
            )
            s.flush()
            if saas_billing.is_configured():
                checkout = saas_billing.crear_checkout_suscripcion(
                    customer_id, nuevo_tid,
                    success_url=url_for("dashboard", _external=True),
                    cancel_url=url_for("suscripcion", _external=True),
                )
                checkout_url = _sval(checkout, "url")
            s.commit()
    except Exception as e:
        logger.error(json.dumps({"event": "signup_error", "slug": slug,
                                 "error": str(e)}, ensure_ascii=False))
        flash("No se pudo completar el alta. No se ha creado ninguna cuenta; "
              "inténtalo de nuevo.", "danger")
        return render_template("signup.html", nombre=nombre, email=email,
                               usuario=admin_user), 502

    # Auditoría de plataforma (taller_id explícito; evento del nuevo taller).
    registrar_auditoria("signup_taller", admin_user,
                        {"taller_id": nuevo_tid, "slug": slug, "email": email})

    # B3.2: enviar verificación de email (NO bloqueante; el taller ya puede usar
    # la app durante el trial, con un aviso para verificar).
    try:
        _vtoken = account_tokens.generar_token_verificacion(nuevo_tid, email)
        _vurl = url_for("auth.verificar_email", token=_vtoken, _external=True)
        notificador.enviar_email("send_email_verificacion", email, _vurl, nombre)
    except Exception as e:
        logger.error(json.dumps({"event": "signup_verif_email_error",
                                 "error": str(e)}, ensure_ascii=False))

    # Log in inmediato: el taller entra en 'trial' y puede usar la app.
    session["usuario"] = admin_user
    session["rol"] = "admin"
    session["permisos"] = obtener_permisos_usuario("admin")
    session["taller_id"] = nuevo_tid
    session["taller_slug"] = slug

    if checkout_url:
        # A Stripe Checkout a por la tarjeta (requerida durante el trial).
        return redirect(checkout_url)
    flash("¡Bienvenido a Kintsu! Tu prueba de 14 días está activa.", "success")
    return redirect(url_for("dashboard"))


@app.route("/suscripcion")
@login_required
def suscripcion():
    """Hub de facturación del taller: estado de la suscripción y gestión.

    El botón al Stripe Customer Portal se añade en 3b.5.
    """
    with get_session() as s:
        taller = s.execute(
            text("SELECT id, nombre, estado, trial_fin, stripe_customer_id "
                 "FROM talleres WHERE id = :tid"),
            {"tid": session.get("taller_id")},
        ).mappings().first()
    return render_template("suscripcion.html", taller=taller)


@app.route("/suscripcion/bloqueado")
def suscripcion_bloqueado():
    """Página mostrada cuando la suscripción del taller no está activa.

    NO borra ni expone datos: sólo informa y enlaza al pago/gestión. Los datos
    del taller siguen intactos y se recuperan en cuanto regulariza el pago.
    """
    estado = None
    tid = session.get("taller_id")
    if tid:
        with get_session() as s:
            row = s.execute(
                text("SELECT estado FROM talleres WHERE id = :t"), {"t": tid}
            ).first()
            estado = row[0] if row else None
    return render_template("suscripcion_bloqueado.html", estado=estado), 402


@app.route("/suscripcion/portal")
@login_required
def suscripcion_portal():
    """Redirige al Stripe Customer Portal para gestionar pago/cancelación (3b.5)."""
    with get_session() as s:
        row = s.execute(
            text("SELECT stripe_customer_id FROM talleres WHERE id = :tid"),
            {"tid": session.get("taller_id")},
        ).first()
    customer_id = row[0] if row else None
    if not customer_id or not saas_billing.is_configured():
        flash("Aún no hay un método de pago asociado a tu cuenta.", "info")
        return redirect(url_for("suscripcion"))
    try:
        portal = saas_billing.crear_portal(
            customer_id, return_url=url_for("suscripcion", _external=True)
        )
        return redirect(_sval(portal, "url"))
    except Exception as e:
        logger.error(json.dumps({"event": "portal_error", "error": str(e)},
                                ensure_ascii=False))
        flash("No se pudo abrir el portal de gestión. Inténtalo más tarde.", "danger")
        return redirect(url_for("suscripcion"))


def _taller_por_customer(s, customer_id):
    """taller_id cuyo stripe_customer_id coincide, o None. SQL crudo (talleres
    no lleva scope de taller)."""
    if not customer_id:
        return None
    row = s.execute(
        text("SELECT id FROM talleres WHERE stripe_customer_id = :c"),
        {"c": customer_id},
    ).first()
    return row[0] if row else None


def _saas_aplicar_evento(s, etype, obj):
    """Aplica un evento de suscripción al Taller. Devuelve (taller_id,
    nuevo_estado, sub_id). NO toca reparaciones ni ningún dato de cliente."""
    customer_id = obj.get("customer")
    tid = _taller_por_customer(s, customer_id)
    if tid is None and etype == "checkout.session.completed":
        meta = obj.get("metadata") or {}
        if meta.get("taller_id"):
            try:
                tid = int(meta["taller_id"])
            except (TypeError, ValueError):
                tid = None
    if tid is None:
        return None, None, None

    nuevo_estado = None
    sub_id = None
    if etype == "checkout.session.completed":
        sub_id = obj.get("subscription")
        nuevo_estado = "trial"  # alta completada con tarjeta; sigue en prueba
    elif etype == "customer.subscription.updated":
        sub_id = obj.get("id")
        nuevo_estado = saas_billing.estado_por_status_stripe(obj.get("status"))
    elif etype == "customer.subscription.deleted":
        sub_id = obj.get("id")
        nuevo_estado = "cancelado"   # suscripción eliminada → acceso bloqueado
    elif etype == "invoice.payment_failed":
        nuevo_estado = "suspendido"  # política: impago → bloqueo (datos intactos)
    elif etype == "invoice.paid":
        # Reactivar SÓLO si estaba suspendido (no degrada un trial al pagar el
        # invoice de 0 € del inicio de prueba).
        cur = s.execute(text("SELECT estado FROM talleres WHERE id = :t"),
                        {"t": tid}).scalar()
        if cur == "suspendido":
            nuevo_estado = "activo"
    else:
        return tid, None, None  # evento no manejado

    if nuevo_estado is None:
        return tid, None, sub_id

    sets = ["estado = :est"]
    params = {"t": tid, "est": nuevo_estado}
    if sub_id:
        sets.append("stripe_sub_id = :sub")
        params["sub"] = sub_id
    s.execute(text(f"UPDATE talleres SET {', '.join(sets)} WHERE id = :t"), params)
    return tid, nuevo_estado, sub_id


@app.route("/saas/webhook", methods=["POST"])
def saas_webhook():
    """Webhook de la SUSCRIPCIÓN del SaaS — SEPARADO del de reparaciones.

    - Verifica la firma con STRIPE_SAAS_WEBHOOK_SECRET (saas_billing).
    - Idempotente: el `event_id` se inserta en `stripe_eventos` dentro de la
      MISMA transacción que el efecto; si Stripe reenvía el evento, el UNIQUE
      choca y no se repite nada.
    - Sincroniza Taller.estado. NUNCA toca reparaciones.
    """
    payload = request.data
    sig = request.headers.get("Stripe-Signature")

    if not saas_billing.STRIPE_SAAS_WEBHOOK_SECRET:
        logger.error("[SAAS-WEBHOOK] STRIPE_SAAS_WEBHOOK_SECRET no configurado")
        return jsonify({"error": "SaaS webhook secret not configured"}), 400
    if not sig:
        return jsonify({"error": "Missing Stripe-Signature header"}), 400

    try:
        event = saas_billing.construir_evento(payload, sig)
    except Exception as e:
        logger.error(json.dumps({"event": "saas_webhook_bad_signature",
                                 "error": str(e)}, ensure_ascii=False))
        return jsonify({"error": str(e)}), 400

    etype = event.get("type")
    eid = event.get("id")
    obj = (event.get("data") or {}).get("object", {}) or {}

    try:
        with get_session() as s:
            # Guarda de idempotencia + efecto en una sola transacción.
            ins = s.execute(
                insert_or_ignore(StripeEvento)
                .values(event_id=eid, tipo=etype,
                        recibido_en=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                .on_conflict_do_nothing()
            )
            if eid and ins.rowcount == 0:
                s.rollback()
                logger.info(json.dumps({"event": "saas_webhook_duplicate",
                                        "stripe_event": eid}, ensure_ascii=False))
                return jsonify({"status": "duplicate"}), 200

            taller_id, nuevo_estado, sub_id = _saas_aplicar_evento(s, etype, obj)
            if taller_id is not None:
                s.execute(
                    text("UPDATE stripe_eventos SET taller_id = :t WHERE event_id = :e"),
                    {"t": taller_id, "e": eid},
                )
            s.commit()
    except Exception as e:
        logger.error(json.dumps({"event": "saas_webhook_error", "type": etype,
                                 "error": str(e)}, ensure_ascii=False))
        return jsonify({"error": str(e)}), 500

    if taller_id is not None and nuevo_estado is not None:
        registrar_auditoria(f"saas_{etype}", "stripe",
                            {"taller_id": taller_id, "estado": nuevo_estado,
                             "subscription": sub_id},
                            taller_id=taller_id)
        logger.info(json.dumps({"event": "saas_webhook_processed", "type": etype,
                                "taller_id": taller_id, "estado": nuevo_estado},
                               ensure_ascii=False))
    return jsonify({"status": "ok"}), 200

# =========================================
# 🔸 PÁGINAS PROTEGIDAS
# =========================================

# HEALTHCHECK — endpoint ligero para diagnosticar deploys en Railway.
# No toca BD, no toca SMTP, no depende de sesion. Si esto devuelve 200, el
# worker esta vivo; si devuelve 502, gunicorn no arranca.
@app.route("/health")
def healthcheck():
    # Liveness + readiness ligero: comprueba la conexión a BD con un SELECT 1.
    # Devuelve 200 siempre (el proceso está vivo) e informa del estado de la BD
    # en "database"; así un parpadeo de BD no tira el healthcheck del hosting.
    db_ok = True
    try:
        with get_session() as s:
            s.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
        logger.warning('{"event": "health_db_unavailable"}')
    return jsonify({
        "status": "ok",
        "database": "ok" if db_ok else "unavailable",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "mail_configured": bool(MAIL_CONFIGURED),
        "python": f"{os.sys.version_info.major}.{os.sys.version_info.minor}",
    }), 200

# PÁGINA PRINCIPAL
# Escaparate + portal del cliente: ahora en blueprints/publico.py (refactor B1).
from blueprints.publico import bp as publico_bp  # noqa: E402

app.register_blueprint(publico_bp)


# =========================================
# 🔸 DASHBOARD
# =========================================

@app.route("/dashboard")
@login_required
def dashboard():
    # Fase 2.4: las ~20 queries del dashboard son raw SQL → NO las alcanza el
    # filtro automático del ORM. Cada una lleva el filtro MANUAL taller_id=:tid.
    from sqlalchemy import text as _text
    tp = {"tid": g.taller_id}
    s = get_session()

    # ========== ESTADÍSTICAS GENERALES ==========
    total_clientes = s.execute(_text("SELECT COUNT(*) FROM clientes WHERE taller_id = :tid"), tp).scalar()
    total_reparaciones = s.execute(_text("SELECT COUNT(*) FROM reparaciones WHERE taller_id = :tid"), tp).scalar()

    reparaciones_activas = s.execute(_text("""
        SELECT COUNT(*) FROM reparaciones
        WHERE taller_id = :tid AND estado != 'Terminado' AND estado != 'Entregado'
    """), tp).scalar()

    reparaciones_terminadas = s.execute(_text("""
        SELECT COUNT(*) FROM reparaciones
        WHERE taller_id = :tid AND (estado = 'Terminado' OR estado = 'Entregado')
    """), tp).scalar()

    # Ingresos totales
    ingresos_total = s.execute(_text("""
        SELECT COALESCE(SUM(precio), 0) FROM reparaciones
        WHERE taller_id = :tid AND precio IS NOT NULL
    """), tp).scalar()

    # ========== ESTADÍSTICAS DE ESTE MES ==========
    hoy = datetime.now()
    inicio_mes = datetime(hoy.year, hoy.month, 1)

    ingresos_mes = s.execute(_text("""
        SELECT COALESCE(SUM(precio), 0) FROM reparaciones
        WHERE taller_id = :tid AND fecha_entrada >= :inicio AND precio IS NOT NULL
    """), {**tp, "inicio": inicio_mes.strftime("%Y-%m-%d")}).scalar()

    reparaciones_mes = s.execute(_text("""
        SELECT COUNT(*) FROM reparaciones
        WHERE taller_id = :tid AND fecha_entrada >= :inicio
    """), {**tp, "inicio": inicio_mes.strftime("%Y-%m-%d")}).scalar()

    reparaciones_completadas_mes = s.execute(_text("""
        SELECT COUNT(*) FROM reparaciones
        WHERE taller_id = :tid AND (estado = 'Terminado' OR estado = 'Entregado')
        AND fecha_entrada >= :inicio
    """), {**tp, "inicio": inicio_mes.strftime("%Y-%m-%d")}).scalar()

    # ========== ESTADÍSTICAS DE PAGOS ==========
    dinero_cobrado = s.execute(_text("""
        SELECT COALESCE(SUM(precio), 0) FROM reparaciones
        WHERE taller_id = :tid AND estado_pago = 'Pagado' AND precio IS NOT NULL
    """), tp).scalar()

    dinero_por_cobrar = ingresos_total - dinero_cobrado

    reparaciones_pendiente_pago = s.execute(_text("""
        SELECT COUNT(*) FROM reparaciones
        WHERE taller_id = :tid AND estado_pago = 'Pendiente' AND precio IS NOT NULL AND precio > 0
    """), tp).scalar()

    reparaciones_pagadas = s.execute(_text("""
        SELECT COUNT(*) FROM reparaciones
        WHERE taller_id = :tid AND estado_pago = 'Pagado'
    """), tp).scalar()

    # Calcular tasa de cobro (porcentaje)
    tasa_cobro = 0
    if ingresos_total > 0:
        tasa_cobro = round((dinero_cobrado / ingresos_total * 100), 1)

    # Obtener reparaciones pendientes de pago (últimas 5)
    reparaciones_sin_pagar = s.execute(_text("""
        SELECT reparaciones.*, clientes.nombre AS cliente
        FROM reparaciones
        LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id
        WHERE reparaciones.taller_id = :tid AND reparaciones.estado_pago = 'Pendiente'
        AND reparaciones.precio IS NOT NULL AND reparaciones.precio > 0
        ORDER BY reparaciones.id DESC
        LIMIT 5
    """), tp).mappings().all()
    reparaciones_sin_pagar_list = [dict(r) for r in reparaciones_sin_pagar] if reparaciones_sin_pagar else []

    # ========== DISPOSITIVOS MÁS REPARADOS ==========
    dispositivos_top = s.execute(_text("""
        SELECT dispositivo, COUNT(*) as cantidad
        FROM reparaciones
        WHERE taller_id = :tid AND dispositivo IS NOT NULL AND dispositivo != ''
        GROUP BY dispositivo
        ORDER BY cantidad DESC, dispositivo ASC
        LIMIT 5
    """), tp).all()

    # ========== ESTADOS MÁS COMUNES ==========
    estados_distribucion = s.execute(_text("""
        SELECT estado, COUNT(*) as cantidad
        FROM reparaciones
        WHERE taller_id = :tid
        GROUP BY estado
        ORDER BY cantidad DESC, estado ASC
    """), tp).all()

    # Convertir a dict para template
    dispositivos_dict = [{"nombre": d[0], "cantidad": d[1]} for d in dispositivos_top] if dispositivos_top else []
    estados_dict = [{"nombre": e[0], "cantidad": e[1]} for e in estados_distribucion] if estados_distribucion else []

    # Calcular porcentajes
    total_rep = reparaciones_activas + reparaciones_terminadas
    porcentaje_activas = round((reparaciones_activas / total_rep * 100), 1) if total_rep > 0 else 0
    porcentaje_terminadas = round((reparaciones_terminadas / total_rep * 100), 1) if total_rep > 0 else 0

    # Últimas 5 reparaciones
    ultimas_reparaciones = s.execute(_text("""
        SELECT reparaciones.*, clientes.nombre AS cliente
        FROM reparaciones
        LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id
        WHERE reparaciones.taller_id = :tid
        ORDER BY reparaciones.id DESC
        LIMIT 5
    """), tp).mappings().all()

    # ========== REPARACIONES ATRASADAS (sin actualización hace > 7 días) ==========
    hace_7_dias = (hoy - __import__('datetime').timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    # ⚠️ El filtro taller_id envuelve TODA la condición original: el OR del
    # final tiene menor precedencia, así que sin el paréntesis externo
    # `... OR (subq)=0` se saldría del scope y filtraría reparaciones de otro
    # taller sin historial. taller_id AND ( <condición original> ) lo evita.
    reparaciones_atrasadas = s.execute(_text("""
        SELECT reparaciones.*, clientes.nombre AS cliente,
               (SELECT fecha_cambio FROM reparaciones_historial
                WHERE reparacion_id = reparaciones.id
                ORDER BY fecha_cambio DESC LIMIT 1) AS ultima_actualizacion
        FROM reparaciones
        LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id
        WHERE reparaciones.taller_id = :tid AND (
            reparaciones.estado IN ('En proceso', 'Pendiente')
            AND (
                SELECT fecha_cambio FROM reparaciones_historial
                WHERE reparacion_id = reparaciones.id
                ORDER BY fecha_cambio DESC LIMIT 1
            ) < :hace7
            OR (
                SELECT COUNT(*) FROM reparaciones_historial
                WHERE reparacion_id = reparaciones.id
            ) = 0
        )
        ORDER BY reparaciones.id DESC
    """), {**tp, "hace7": hace_7_dias}).mappings().all()

    reparaciones_atrasadas_list = [dict(r) for r in reparaciones_atrasadas] if reparaciones_atrasadas else []

    # Enriquecer con alertas
    for rep in reparaciones_sin_pagar_list:
        rep['alertas_info'] = calcular_alertas_reparacion(rep, rep.get('ultima_actualizacion'))

    for rep in reparaciones_atrasadas_list:
        rep['alertas_info'] = calcular_alertas_reparacion(rep, rep.get('ultima_actualizacion'))

    # ========== MÉTRICA 1: INGRESOS POR MES (últimos 6 meses) ==========
    ingresos_por_mes = []
    for i in range(5, -1, -1):  # Últimos 6 meses
        fecha = hoy - __import__('datetime').timedelta(days=30*i)
        inicio = datetime(fecha.year, fecha.month, 1)
        if i == 0:
            fin = hoy
        else:
            # Primer día del mes siguiente
            if fecha.month == 12:
                fin = datetime(fecha.year + 1, 1, 1) - __import__('datetime').timedelta(seconds=1)
            else:
                fin = datetime(fecha.year, fecha.month + 1, 1) - __import__('datetime').timedelta(seconds=1)

        ingreso_mes_i = s.execute(_text("""
            SELECT COALESCE(SUM(precio), 0) FROM reparaciones
            WHERE taller_id = :tid AND fecha_entrada >= :ini AND fecha_entrada <= :fin AND precio IS NOT NULL
        """), {**tp, "ini": inicio.strftime("%Y-%m-%d"), "fin": fin.strftime("%Y-%m-%d")}).scalar()

        ingresos_por_mes.append({
            "mes": inicio.strftime("%b %Y"),
            # float() para que el repr sea idéntico entre motores: SQLite
            # devuelve int 0 cuando no hay filas y Postgres 0.0 (mismo valor,
            # distinto repr); la coerción los iguala (Fase 3a.5, pincho A).
            "valor": round(float(ingreso_mes_i), 2)
        })

    # ========== MÉTRICA 2: TIEMPO MEDIO DE REPARACIÓN ==========
    tiempo_medio_dias = 0
    reparaciones_completadas = s.execute(_text("""
        SELECT COUNT(*) FROM reparaciones
        WHERE taller_id = :tid AND (estado = 'Terminado' OR estado = 'Entregado')
    """), tp).scalar()

    if reparaciones_completadas > 0:
        # Calcular promedio de días entre entrada y última actualización.
        # ⚠️ Pincho A: julianday() es SQLite-only. Las fechas son TEXT en ambos
        # motores; el cálculo de "días entre" se ramifica por dialecto:
        #   SQLite   → julianday(a) - julianday(b)
        #   Postgres → EXTRACT(EPOCH FROM (a::timestamp - b::timestamp)) / 86400
        if is_postgres():
            _dif_dias = ("EXTRACT(EPOCH FROM (CAST({a} AS timestamp) "
                         "- CAST(reparaciones.fecha_entrada AS timestamp))) / 86400.0")
        else:
            _dif_dias = "julianday({a}) - julianday(reparaciones.fecha_entrada)"
        _ultima = ("COALESCE((SELECT fecha_cambio FROM reparaciones_historial "
                   "WHERE reparacion_id = reparaciones.id "
                   "ORDER BY fecha_cambio DESC LIMIT 1), reparaciones.fecha_entrada)")
        tiempo_promedio = s.execute(_text(f"""
            SELECT AVG(CAST(({_dif_dias.format(a=_ultima)}) AS REAL))
            FROM reparaciones
            WHERE taller_id = :tid AND (estado = 'Terminado' OR estado = 'Entregado')
        """), tp).scalar()

        if tiempo_promedio:
            tiempo_medio_dias = round(float(tiempo_promedio), 1)

    # ========== MÉTRICA 3: REPARACIONES POR TÉCNICO ==========
    # reparaciones_historial lleva taller_id desnormalizado → filtro directo.
    reparaciones_por_tecnico = s.execute(_text("""
        SELECT usuario, COUNT(*) as cantidad
        FROM reparaciones_historial
        WHERE taller_id = :tid AND usuario IS NOT NULL AND usuario != ''
        GROUP BY usuario
        ORDER BY cantidad DESC
    """), tp).all()

    tecnico_dict = [{"nombre": t[0], "cantidad": t[1]} for t in reparaciones_por_tecnico] if reparaciones_por_tecnico else []

    # ========== AUDITORÍA RECIENTE (últimos 10 eventos) ==========
    eventos_auditoria = obtener_auditoria_reciente(limite=10)

    s.close()

    # Calcular IVA en ingresos
    iva_total = round(ingresos_total * 0.21, 2)
    iva_mes = round(ingresos_mes * 0.21, 2)

    _dias = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
    _meses = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']
    _ahora = datetime.now()
    now = f"{_dias[_ahora.weekday()]} {_ahora.day} de {_meses[_ahora.month-1]} de {_ahora.year}, {_ahora.strftime('%H:%M')}"

    return render_template(
        "dashboard.html",
        now=now,
        total_clientes=total_clientes,
        total_reparaciones=total_reparaciones,
        reparaciones_activas=reparaciones_activas,
        reparaciones_terminadas=reparaciones_terminadas,
        porcentaje_activas=porcentaje_activas,
        porcentaje_terminadas=porcentaje_terminadas,
        ingresos_total=round(ingresos_total, 2),
        iva_total=iva_total,
        ingresos_mes=round(ingresos_mes, 2),
        iva_mes=iva_mes,
        reparaciones_mes=reparaciones_mes,
        reparaciones_completadas_mes=reparaciones_completadas_mes,
        ultimas_reparaciones=ultimas_reparaciones,
        dispositivos_top=dispositivos_dict,
        estados_distribucion=estados_dict,
        dinero_cobrado=round(dinero_cobrado, 2),
        dinero_por_cobrar=round(dinero_por_cobrar, 2),
        reparaciones_pendiente_pago=reparaciones_pendiente_pago,
        reparaciones_pagadas=reparaciones_pagadas,
        tasa_cobro=tasa_cobro,
        reparaciones_sin_pagar=reparaciones_sin_pagar_list,
        reparaciones_atrasadas=reparaciones_atrasadas_list,
        ingresos_por_mes=ingresos_por_mes,
        tiempo_medio_dias=tiempo_medio_dias,
        reparaciones_por_tecnico=tecnico_dict,
        eventos_auditoria=eventos_auditoria,
        user_role=session.get('rol')
    )

#  SECCIÓN CLIENTES

# LISTAR CLIENTES



# Dominio clientes: ahora en blueprints/clientes.py (refactor B1).
from blueprints.clientes import bp as clientes_bp  # noqa: E402

app.register_blueprint(clientes_bp)


# =========================================
#  🔸 EXPORTAR CSV
# =========================================

import csv
from io import BytesIO, StringIO

# Helpers de exportación CSV: extraídos a csv_utils.py (refactor B1).
from csv_utils import (  # noqa: E402
    _SEP_CSV,
    _csv_empresa_header,
    _csv_filename_prefix,
    _csv_pie,
    _fmt_fecha_csv,
    _fmt_precio_csv,
)


@app.route("/exportar/reparaciones.csv")
@login_required
@permiso_requerido('reparaciones_exportar')
def exportar_reparaciones_csv():
    # Fase 2.4: filtro MANUAL de taller (raw SQL con subqueries).
    from sqlalchemy import text as _text
    with get_session() as s:
        rows = s.execute(_text('''
            SELECT r.id, c.nombre as cliente, c.email, c.telefono, c.direccion,
                   r.dispositivo, r.descripcion, r.estado, r.estado_pago,
                   r.precio, r.fecha_entrada, r.fecha_salida, r.fecha_pago, r.metodo_pago,
                   r.tipo_documento,
                   (SELECT COUNT(*) FROM fotos_reparacion WHERE reparacion_id = r.id) as num_fotos,
                   (SELECT COUNT(*) FROM notas_reparacion WHERE reparacion_id = r.id) as num_notas,
                   CASE WHEN r.firma IS NOT NULL AND r.firma != '' THEN 'Si' ELSE 'No' END as firmado
            FROM reparaciones r
            LEFT JOIN clientes c ON r.cliente_id = c.id
            WHERE r.taller_id = :tid
            ORDER BY r.id DESC
        '''), {"tid": g.taller_id}).mappings().all()

    total = len(rows)
    total_facturado  = sum(r['precio'] or 0 for r in rows)
    total_pagado     = sum(r['precio'] or 0 for r in rows if r['estado_pago'] == 'Pagado')
    total_pendiente  = total_facturado - total_pagado
    n_pendiente      = sum(1 for r in rows if r['estado'] == 'Pendiente')
    n_en_proceso     = sum(1 for r in rows if r['estado'] == 'En proceso')
    n_terminado      = sum(1 for r in rows if r['estado'] == 'Terminado')
    n_entregado      = sum(1 for r in rows if r['estado'] == 'Entregado')

    si = StringIO()
    w  = csv.writer(si, delimiter=';')

    # ── Cabecera corporativa ──────────────────────────────────────────────────
    _csv_empresa_header(w, 'INFORME COMPLETO DE REPARACIONES')

    # ── Resumen ejecutivo ─────────────────────────────────────────────────────
    w.writerow(['--- RESUMEN ---'])
    w.writerow(['Total reparaciones', total])
    w.writerow(['Total facturado',    _fmt_precio_csv(total_facturado)])
    w.writerow(['Total cobrado',      _fmt_precio_csv(total_pagado)])
    w.writerow(['Pendiente de cobro', _fmt_precio_csv(total_pendiente)])
    w.writerow([])
    w.writerow(['Estado', 'Cantidad'])
    w.writerow(['Pendiente',   n_pendiente])
    w.writerow(['En proceso',  n_en_proceso])
    w.writerow(['Terminado',   n_terminado])
    w.writerow(['Entregado',   n_entregado])
    w.writerow([])

    # ── Datos ─────────────────────────────────────────────────────────────────
    w.writerow(['--- DETALLE DE REPARACIONES ---'])
    w.writerow([
        'N. Reparacion', 'Cliente', 'Email', 'Telefono', 'Direccion',
        'Dispositivo', 'Descripcion', 'Estado', 'Estado Pago',
        'Precio', 'Tipo Documento', 'Fecha Entrada', 'Fecha Salida',
        'Fecha Pago', 'Metodo Pago', 'Fotos', 'Notas', 'Firmado',
    ])

    for r in rows:
        w.writerow([
            r['id'],
            r['cliente']       or 'Sin asignar',
            r['email']         or '',
            r['telefono']      or '',
            r['direccion']     or '',
            r['dispositivo'],
            r['descripcion']   or '',
            r['estado'],
            r['estado_pago'],
            _fmt_precio_csv(r['precio']),
            r['tipo_documento'] or '',
            _fmt_fecha_csv(r['fecha_entrada']),
            _fmt_fecha_csv(r['fecha_salida']),
            _fmt_fecha_csv(r['fecha_pago']),
            r['metodo_pago']   or '',
            r['num_fotos'],
            r['num_notas'],
            r['firmado'],
        ])

    # ── Pie ───────────────────────────────────────────────────────────────────
    w.writerow([])
    w.writerow([_SEP_CSV])
    _csv_pie(w)
    w.writerow([_SEP_CSV])

    output = BytesIO()
    output.write(si.getvalue().encode('utf-8-sig'))
    output.seek(0)
    return send_file(output, mimetype='text/csv', as_attachment=True,
                     download_name=f'{_csv_filename_prefix()}_Reparaciones_{datetime.now().strftime("%Y%m%d_%H%M")}.csv')


# =========================================
#  🔸 SECCIÓN REPARACIONES
# =========================================

# LISTAR REPARACIONES
@app.route("/reparaciones")
@login_required
def reparaciones():
    # Recoger filtros desde query string
    cliente_id = request.args.get('cliente_id', '').strip()
    estado = request.args.get('estado', '').strip()
    desde = request.args.get('desde', '').strip()
    hasta = request.args.get('hasta', '').strip()
    precio_min = request.args.get('precio_min', '').strip()
    precio_max = request.args.get('precio_max', '').strip()
    # búsqueda global
    q = request.args.get('q', '').strip()

    # Fase 2.4: SQL dinámico con filtro de taller SIEMPRE presente (raw SQL).
    from sqlalchemy import text as _text

    sql_base = "FROM reparaciones LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id"

    # El filtro de taller es la primera cláusula y nunca falta.
    where_clauses = ["reparaciones.taller_id = :tid"]
    params = {"tid": g.taller_id}

    if cliente_id:
        where_clauses.append("reparaciones.cliente_id = :cliente_id")
        params['cliente_id'] = cliente_id

    if estado:
        where_clauses.append("reparaciones.estado = :estado")
        params['estado'] = estado

    if q:
        q_clauses = []
        # buscar por ID exacta si es numérico
        try:
            params['q_id'] = int(q)
            q_clauses.append("reparaciones.id = :q_id")
        except ValueError:
            pass
        q_clauses.append("clientes.nombre LIKE :q_like")
        q_clauses.append("clientes.telefono LIKE :q_like")
        params['q_like'] = f"%{q}%"
        where_clauses.append("(" + " OR ".join(q_clauses) + ")")

    if desde:
        where_clauses.append("reparaciones.fecha_entrada >= :desde")
        params['desde'] = desde

    if hasta:
        where_clauses.append("reparaciones.fecha_entrada <= :hasta")
        params['hasta'] = hasta

    if precio_min:
        try:
            params['precio_min'] = float(precio_min)
            where_clauses.append("reparaciones.precio >= :precio_min")
        except ValueError:
            pass

    if precio_max:
        try:
            params['precio_max'] = float(precio_max)
            where_clauses.append("reparaciones.precio <= :precio_max")
        except ValueError:
            pass

    where_sql = " WHERE " + " AND ".join(where_clauses)

    with get_session() as s:
        # Total para paginación (COUNT scoped por taller: el WHERE ya incluye
        # reparaciones.taller_id = :tid, así que el contador es del taller).
        total = s.execute(
            _text("SELECT COUNT(*) " + sql_base + where_sql), params
        ).scalar()

        # Paginación centralizada (B5): PAGE_SIZE por env, clamp de rango.
        pag = paginar(total)

        # Consulta principal con orden y límite (tiebreak por id para orden
        # determinista entre páginas cuando hay fechas repetidas).
        select_sql = ("SELECT reparaciones.*, clientes.nombre AS cliente " + sql_base
                      + where_sql + " ORDER BY fecha_entrada DESC, reparaciones.id DESC "
                      + "LIMIT :limit OFFSET :offset")
        datos = s.execute(
            _text(select_sql), {**params, 'limit': pag.per_page, 'offset': pag.offset}
        ).mappings().all()

        # Enriquecer con la última actualización de cada reparación SIN N+1:
        # una sola consulta agregada para todas las filas de la página (P1).
        ultimas = _ultimas_actualizaciones(s, [r['id'] for r in datos])
        datos_enriquecidos = []
        for r in datos:
            r_dict = dict(r)
            r_dict['ultima_actualizacion'] = ultimas.get(r_dict['id'])
            # Calcular alertas inteligentes
            r_dict['alertas_info'] = calcular_alertas_reparacion(r_dict, r_dict['ultima_actualizacion'])
            datos_enriquecidos.append(r_dict)

        # Lista de clientes para filtro (ORM)
        clientes = s.scalars(select(Cliente).order_by(Cliente.nombre)).all()

    # Construir query string de filtros (sin page)
    filters = {}
    if cliente_id:
        filters['cliente_id'] = cliente_id
    if estado:
        filters['estado'] = estado
    if desde:
        filters['desde'] = desde
    if hasta:
        filters['hasta'] = hasta
    if precio_min:
        filters['precio_min'] = precio_min
    if precio_max:
        filters['precio_max'] = precio_max
    if q:
        filters['q'] = q

    filters_query = urllib.parse.urlencode(filters)

    # Determinar si mostrar precios según rol
    mostrar_precios = session.get('rol') in ['admin', 'tecnico']

    return render_template("reparaciones.html", reparaciones=datos_enriquecidos, clientes=clientes, filters=filters, filters_query=filters_query, pagina=pag, page=pag.page, total_pages=pag.total_pages, per_page=pag.per_page, total=total, mostrar_precios=mostrar_precios, user_role=session.get('rol'))


# NUEVA REPARACIÓN
@app.route("/reparaciones/nueva", methods=["GET", "POST"])
@login_required
@csrf_protect
def nueva_reparacion():
    if request.method == "POST":
        cliente_id = request.form["cliente_id"]
        dispositivo = request.form["dispositivo"]
        descripcion = request.form["descripcion"]
        estado = request.form["estado"]
        precio = request.form.get("precio")

        fecha_entrada = datetime.now().strftime("%Y-%m-%d")

        # validar precio using helper
        if precio:
            if not validar_precio(precio):
                flash('Precio inválido', 'danger')
                return redirect(url_for('nueva_reparacion'))
            if session.get('rol') != 'admin':
                precio = None
            else:
                precio = float(precio)
        else:
            precio = None

        with get_session() as s:
            rep = Reparacion(
                cliente_id=cliente_id, dispositivo=dispositivo,
                descripcion=descripcion, estado=estado,
                fecha_entrada=fecha_entrada, precio=precio,
            )
            s.add(rep)
            s.commit()
            new_id = rep.id

            # Guardar fotos subidas
            fotos = request.files.getlist('fotos')
            for foto in fotos:
                if foto and foto.filename and allowed_file(foto.filename) and es_imagen_valida(foto):
                    ext = foto.filename.rsplit('.', 1)[1].lower()
                    unique_name = f"{new_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}.{ext}"
                    foto.save(os.path.join(uploads.UPLOAD_FOLDER, unique_name))
                    s.add(FotoReparacion(
                        reparacion_id=new_id, filename=unique_name,
                        descripcion='',
                        fecha_subida=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        subido_por=session.get('usuario'),
                    ))
            s.commit()

            # Datos del cliente para el email (antes de cerrar la sesión)
            cliente = s.get(Cliente, cliente_id)
            cliente_nombre = cliente.nombre if cliente else None
            cliente_email = cliente.email if cliente else None

        try:
            logger.info(json.dumps({
                "event": "reparacion_created",
                "reparacion_id": new_id,
                "cliente_id": cliente_id,
                "dispositivo": dispositivo,
                "usuario": session.get('usuario')
            }, ensure_ascii=False))
        except Exception:
            logger.info(f"reparacion_created id={new_id} cliente={cliente_id} device={dispositivo}")

        # Enviar email de nueva reparación al cliente
        try:
            if cliente_email:
                notificador.enviar_email("send_nueva_reparacion",
                    to_email=cliente_email,
                    cliente_nombre=cliente_nombre,
                    reparacion_id=new_id,
                    dispositivo=dispositivo,
                    descripcion=descripcion,
                    fecha_entrada=fecha_entrada
                )
                logger.info(f"Email de nueva reparacion enviado para reparacion {new_id}")
        except Exception as e:
            logger.error(f"Error enviando email de nueva reparacion: {type(e).__name__}: {str(e)}")

        return redirect(url_for("reparaciones"))

    with get_session() as s:
        clientes = s.scalars(select(Cliente)).all()

    return render_template("nueva_reparacion.html", clientes=clientes)


# EDITAR REPARACIÓN
@app.route("/reparaciones/editar/<int:id>", methods=["GET", "POST"])
@login_required
@csrf_protect
def editar_reparacion(id):
    if request.method == "POST":
        cliente_id = request.form["cliente_id"]
        dispositivo = request.form["dispositivo"]
        descripcion = request.form["descripcion"]
        estado = request.form["estado"]
        precio = request.form["precio"]

        with get_session() as s:
            rep = s.get(Reparacion, id)

            # Validar transición de estado
            estado_anterior = rep.estado
            transicion_valida, error_transicion = validar_transicion(
                estado_anterior, estado, rol=session.get('rol', 'tecnico')
            )
            if not transicion_valida:
                flash(error_transicion, 'danger')
                return redirect(url_for('editar_reparacion', id=id))

            # precio validación: solo admin puede cambiar precio
            if precio:
                if not validar_precio(precio):
                    flash('Precio inválido', 'danger')
                    return redirect(url_for('editar_reparacion', id=id))
                precio_val = float(precio)
                if session.get('rol') != 'admin':
                    # si no es admin, no permitimos alterar precio
                    precio = rep.precio
                else:
                    precio = precio_val
            else:
                precio = None

            # Registrar cambio de estado en historial (ANTES de actualizar:
            # registrar_cambio_estado lee el estado vigente de BD en su
            # propia sesión, así que el orden sigue siendo contrato).
            registrar_cambio_estado(id, estado, usuario=session.get('usuario'))

            rep.cliente_id = cliente_id
            rep.dispositivo = dispositivo
            rep.descripcion = descripcion
            rep.estado = estado
            rep.precio = precio
            s.commit()

            # Datos del cliente para el email (tras el update, igual que antes)
            cliente_email = None
            cliente_nombre = None
            cliente_obj = s.get(Cliente, cliente_id)
            if cliente_obj:
                cliente_email = cliente_obj.email
                cliente_nombre = cliente_obj.nombre

        # Enviar email de actualización de estado si cambió
        if estado_anterior != estado:
            try:
                if cliente_email:
                    # Enviar email de actualización de estado
                    notificador.enviar_email("send_repair_status_update",
                        to_email=cliente_email,
                        cliente_nombre=cliente_nombre,
                        reparacion_id=id,
                        estado_anterior=estado_anterior,
                        estado_nuevo=estado,
                        dispositivo=dispositivo,
                        descripcion=descripcion
                    )
                    logger.info(f'[EMAIL] Email de actualizacion de estado enviado a {cliente_email} para reparacion {id}')
                else:
                    logger.warning(f'[EMAIL] ⚠️ No se pudo enviar email de actualización: cliente sin email para reparación {id}')

            except Exception as e:
                logger.exception(f'Error enviando email de actualización de estado para reparación {id}: {str(e)}')

        try:
            logger.info(json.dumps({
                "event": "reparacion_updated",
                "reparacion_id": id,
                "cliente_id": cliente_id,
                "dispositivo": dispositivo,
                "usuario": session.get('usuario')
            }, ensure_ascii=False))
        except Exception:
            logger.info(f"reparacion_updated id={id} cliente={cliente_id} device={dispositivo}")
        return redirect(url_for("reparaciones"))

    # ── GET: cargar la reparación y sus datos asociados vía ORM ──────────
    with get_session() as s:
        # mappings() devuelve filas dict-like: compatible con la plantilla y
        # con calcular_alertas_reparacion (que hace dict(reparacion)).
        # ⚠️ Core select → filtro de taller MANUAL (Fase 2.5).
        reparacion = s.execute(
            select(Reparacion.__table__)
            .where(Reparacion.__table__.c.id == id)
            .where(Reparacion.__table__.c.taller_id == g.taller_id)
        ).mappings().first()
        if not reparacion:
            # id de otro taller (IDOR) o inexistente → 404 limpio, nunca datos.
            abort(404)
        clientes = s.scalars(select(Cliente)).all()

        # Historial completo de estados para timeline
        historial_objs = s.scalars(
            select(RepairHistorial)
            .where(RepairHistorial.reparacion_id == id)
            .order_by(RepairHistorial.fecha_cambio.asc())
        ).all()
        historial = [{
            'estado_anterior': h.estado_anterior,
            'estado_nuevo': h.estado_nuevo,
            'fecha_cambio': h.fecha_cambio,
            'usuario': h.usuario,
        } for h in historial_objs]

        # Obtener fotos de la reparación
        fotos = s.scalars(
            select(FotoReparacion)
            .where(FotoReparacion.reparacion_id == id)
            .order_by(FotoReparacion.fecha_subida.desc())
        ).all()

        # Obtener notas internas
        notas = s.scalars(
            select(NotaReparacion)
            .where(NotaReparacion.reparacion_id == id)
            .order_by(NotaReparacion.fecha_creacion.desc())
        ).all()

        # Obtener piezas usadas en esta reparación (JOIN con inventario).
        # ⚠️ PiezaReparacion.__table__ es Core → filtro de taller MANUAL.
        piezas_rows = s.execute(
            select(
                PiezaReparacion.__table__,
                InventarioPieza.nombre.label('pieza_nombre'),
                InventarioPieza.precio_venta,
            )
            .join(InventarioPieza, PiezaReparacion.pieza_id == InventarioPieza.id)
            .where(PiezaReparacion.__table__.c.taller_id == g.taller_id)
            .where(PiezaReparacion.reparacion_id == id)
            .order_by(PiezaReparacion.fecha_uso.desc())
        ).mappings().all()
        piezas_usadas = [dict(p) for p in piezas_rows]

        # Obtener última actualización para calcular alertas
        ultima_act = s.scalars(
            select(RepairHistorial.fecha_cambio)
            .where(RepairHistorial.reparacion_id == id)
            .order_by(RepairHistorial.fecha_cambio.desc())
            .limit(1)
        ).first()

    # Determinar si puede editar precio según rol
    puede_editar_precio = session.get('rol') == 'admin'

    # Calcular alertas
    alertas_info = calcular_alertas_reparacion(reparacion, ultima_act)

    # Calcular estados disponibles según rol
    from historial import ESTADOS_VALIDOS, TRANSICIONES_VALIDAS
    rol = session.get('rol', 'tecnico')
    estado_actual = reparacion['estado']
    if rol == 'admin':
        estados_disponibles = ESTADOS_VALIDOS
    else:
        estados_disponibles = (estado_actual,) + TRANSICIONES_VALIDAS.get(estado_actual, ())

    return render_template(
        "editar_reparacion.html",
        reparacion=reparacion,
        clientes=clientes,
        puede_editar_precio=puede_editar_precio,
        user_role=session.get('rol'),
        alertas_info=alertas_info,
        historial=historial,
        estados_disponibles=estados_disponibles,
        fotos=fotos,
        notas=notas,
        piezas_usadas=piezas_usadas
    )


# BORRAR REPARACIÓN
@app.route("/reparaciones/borrar/<int:id>")
@login_required
@permiso_requerido('reparaciones_borrar')
def borrar_reparacion(id):
    with get_session() as s:
        rep = s.get(Reparacion, id)

        # Validar que no esté pagada
        if rep and rep.estado_pago == 'Pagado':
            flash('❌ No se puede eliminar: esta reparación ya está pagada.', 'danger')
            return redirect(url_for("reparaciones"))

        # Eliminar fotos asociadas (ficheros físicos + filas)
        fotos = s.scalars(
            select(FotoReparacion).where(FotoReparacion.reparacion_id == id)
        ).all()
        for foto in fotos:
            filepath = os.path.join(uploads.UPLOAD_FOLDER, foto.filename)
            if os.path.exists(filepath):
                os.remove(filepath)
            s.delete(foto)

        if rep:
            s.delete(rep)
        s.commit()
    try:
        logger.info(json.dumps({
            "event": "reparacion_deleted",
            "reparacion_id": id,
            "usuario": session.get('usuario')
        }, ensure_ascii=False))
    except Exception:
        logger.info(f"reparacion_deleted id={id}")
    flash('✅ Reparación eliminada correctamente.', 'success')
    return redirect(url_for("reparaciones"))


# SUBIR FOTOS A REPARACIÓN
@app.route("/reparaciones/<int:id>/fotos", methods=["POST"])
@login_required
@csrf_protect
def subir_fotos_reparacion(id):
    with get_session() as s:
        rep = s.get(Reparacion, id)
        if not rep:
            flash('Reparación no encontrada.', 'danger')
            return redirect(url_for('reparaciones'))

        fotos = request.files.getlist('fotos')
        count = 0
        for foto in fotos:
            if foto and foto.filename and allowed_file(foto.filename) and es_imagen_valida(foto):
                ext = foto.filename.rsplit('.', 1)[1].lower()
                unique_name = f"{id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}.{ext}"
                foto.save(os.path.join(uploads.UPLOAD_FOLDER, unique_name))
                s.add(FotoReparacion(
                    reparacion_id=id, filename=unique_name, descripcion='',
                    fecha_subida=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    subido_por=session.get('usuario'),
                ))
                count += 1

        s.commit()
    if count:
        flash(f'Se subieron {count} foto(s) correctamente.', 'success')
    else:
        flash('No se subieron fotos. Formatos permitidos: PNG, JPG, JPEG, WebP, GIF (max 5MB).', 'warning')
    return redirect(url_for('editar_reparacion', id=id))


# ELIMINAR FOTO DE REPARACIÓN
@app.route("/reparaciones/fotos/<int:foto_id>/eliminar", methods=["POST"])
@login_required
@csrf_protect
def eliminar_foto_reparacion(foto_id):
    with get_session() as s:
        foto = s.get(FotoReparacion, foto_id)
        if not foto:
            flash('Foto no encontrada.', 'danger')
            return redirect(url_for('reparaciones'))

        reparacion_id = foto.reparacion_id

        # Eliminar archivo físico
        filepath = os.path.join(uploads.UPLOAD_FOLDER, foto.filename)
        if os.path.exists(filepath):
            os.remove(filepath)

        s.delete(foto)
        s.commit()
    flash('Foto eliminada correctamente.', 'success')
    return redirect(url_for('editar_reparacion', id=reparacion_id))


# FIRMA DIGITAL DEL CLIENTE
@app.route("/reparaciones/<int:id>/firma", methods=["GET"])
@login_required
def firmar_reparacion(id):
    with get_session() as s:
        reparacion = s.execute(
            select(Reparacion.__table__, Cliente.nombre.label('cliente_nombre'))
            .join(Cliente, Reparacion.cliente_id == Cliente.id)
            .where(Reparacion.__table__.c.taller_id == g.taller_id)  # ⚠️ Core → filtro manual
            .where(Reparacion.id == id)
        ).mappings().first()
    if not reparacion:
        flash('Reparación no encontrada.', 'danger')
        return redirect(url_for('reparaciones'))
    return render_template("firmar_reparacion.html", reparacion=reparacion)


@app.route("/reparaciones/<int:id>/firma", methods=["POST"])
@login_required
def guardar_firma_reparacion(id):
    import base64
    # CSRF check for JSON requests
    csrf_token = request.headers.get('X-CSRFToken', '')
    if not csrf_token or csrf_token != session.get('csrf_token'):
        return jsonify({"error": "Token CSRF inválido"}), 403

    with get_session() as s:
        rep = s.get(Reparacion, id)
        if not rep:
            return jsonify({"error": "Reparación no encontrada"}), 404

        data = request.get_json()
        if not data or not data.get('firma'):
            return jsonify({"error": "No se recibió la firma"}), 400

        # Decodificar base64 PNG
        firma_data = data['firma']
        if ',' in firma_data:
            firma_data = firma_data.split(',')[1]

        try:
            img_bytes = base64.b64decode(firma_data)
        except Exception:
            return jsonify({"error": "Datos de firma inválidos"}), 400

        # H10: validar que es un PNG REAL (magic bytes) y ≤ 5 MB.
        if not img_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return jsonify({"error": "La firma debe ser una imagen PNG válida"}), 400
        if len(img_bytes) > MAX_CONTENT_LENGTH:
            return jsonify({"error": "La firma es demasiado grande"}), 400

        # Eliminar firma anterior si existe
        if rep.firma:
            old_path = os.path.join(uploads.SIGNATURES_FOLDER, rep.firma)
            if os.path.exists(old_path):
                os.remove(old_path)

        # Guardar nueva firma
        filename = f"firma_{id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        filepath = os.path.join(uploads.SIGNATURES_FOLDER, filename)
        with open(filepath, 'wb') as f:
            f.write(img_bytes)

        rep.firma = filename
        s.commit()

    logger.info(f"firma_guardada reparacion_id={id} usuario={session.get('usuario')}")
    return jsonify({"success": True, "filename": filename})


# NOTAS INTERNAS DE REPARACIÓN
@app.route("/reparaciones/<int:id>/notas", methods=["POST"])
@login_required
@csrf_protect
def agregar_nota_reparacion(id):
    with get_session() as s:
        rep = s.get(Reparacion, id)
        if not rep:
            flash('Reparación no encontrada.', 'danger')
            return redirect(url_for('reparaciones'))

        contenido = request.form.get('contenido', '').strip()
        if not contenido:
            flash('La nota no puede estar vacía.', 'warning')
            return redirect(url_for('editar_reparacion', id=id))

        es_importante = 1 if request.form.get('es_importante') else 0

        s.add(NotaReparacion(
            reparacion_id=id, usuario=session.get('usuario'),
            contenido=contenido,
            fecha_creacion=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            es_importante=es_importante,
        ))
        s.commit()
    flash('Nota agregada correctamente.', 'success')
    return redirect(url_for('editar_reparacion', id=id))


@app.route("/reparaciones/notas/<int:nota_id>/eliminar", methods=["POST"])
@login_required
@csrf_protect
def eliminar_nota_reparacion(nota_id):
    with get_session() as s:
        nota = s.get(NotaReparacion, nota_id)
        if not nota:
            flash('Nota no encontrada.', 'danger')
            return redirect(url_for('reparaciones'))

        reparacion_id = nota.reparacion_id
        # Solo el autor o admin pueden eliminar
        if nota.usuario != session.get('usuario') and session.get('rol') != 'admin':
            flash('No tienes permiso para eliminar esta nota.', 'danger')
            return redirect(url_for('editar_reparacion', id=reparacion_id))

        s.delete(nota)
        s.commit()
    flash('Nota eliminada.', 'success')
    return redirect(url_for('editar_reparacion', id=reparacion_id))


# Dominio inventario/piezas: ahora en blueprints/inventario.py (refactor B1).
from blueprints.inventario import bp as inventario_bp  # noqa: E402

app.register_blueprint(inventario_bp)


# ── CALENDARIO DE REPARACIONES ─────────────────────────────────────

@app.route("/calendario")
@login_required
def calendario():
    return render_template("calendario.html")


@app.route("/api/calendario/eventos")
@login_required
def api_calendario_eventos():
    with get_session() as s:
        rows = s.execute(
            select(
                Reparacion.id, Reparacion.dispositivo, Reparacion.estado,
                Reparacion.fecha_entrada, Reparacion.fecha_salida,
                Cliente.nombre.label('cliente'),
            ).join(Cliente, Reparacion.cliente_id == Cliente.id)
        ).mappings().all()

    colores = {
        'Pendiente': '#ffc107',
        'En proceso': '#2B8AC4',
        'Terminado': '#198754',
        'Entregado': '#6c757d'
    }

    eventos = []
    for r in rows:
        eventos.append({
            'id': r['id'],
            'title': f"#{r['id']} {r['dispositivo']}",
            'start': r['fecha_entrada'],
            'end': r['fecha_salida'] if r['fecha_salida'] else None,
            'color': colores.get(r['estado'], '#2B8AC4'),
            'url': f"/reparaciones/editar/{r['id']}",
            'extendedProps': {
                'cliente': r['cliente'],
                'estado': r['estado']
            }
        })
    return jsonify(eventos)


# ── TICKET DE RECOGIDA CON QR ──────────────────────────────────────

@app.route("/reparaciones/<int:id>/ticket")
@login_required
def ticket_recogida(id):
    from io import BytesIO

    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    with get_session() as s:
        reparacion = s.execute(
            select(
                Reparacion.__table__,
                Cliente.nombre.label('cliente_nombre'),
                Cliente.telefono.label('cliente_telefono'),
                Cliente.email.label('cliente_email'),
            ).join(Cliente, Reparacion.cliente_id == Cliente.id)
            .where(Reparacion.__table__.c.taller_id == g.taller_id)  # ⚠️ Core → filtro manual
            .where(Reparacion.id == id)
        ).mappings().first()

    if not reparacion:
        flash('Reparación no encontrada.', 'danger')
        return redirect(url_for('reparaciones'))

    buffer = BytesIO()
    # Half-page ticket size
    page_w = A4[0]
    page_h = A4[1] / 2
    doc = SimpleDocTemplate(buffer, pagesize=(page_w, page_h),
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=1*cm, bottomMargin=1*cm)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TKTitle', parent=styles['Heading1'], fontSize=20,
                               textColor=colors.HexColor('#2B8AC4'), alignment=TA_CENTER, spaceAfter=2))
    styles.add(ParagraphStyle(name='TKSub', parent=styles['Normal'], fontSize=9,
                               textColor=colors.HexColor('#6c757d'), alignment=TA_CENTER, spaceAfter=10))
    styles.add(ParagraphStyle(name='TKCenter', parent=styles['Normal'], fontSize=9,
                               alignment=TA_CENTER))

    elements = []

    # Header — emisor = taller activo
    _marca = taller_branding()
    elements.append(Paragraph(_marca['nombre'] or 'Taller', styles['TKTitle']))
    elements.append(Paragraph("TICKET DE RECOGIDA", styles['TKSub']))

    # QR code: URL directa a la consulta de esta reparacion
    # request.host_url ya incluye esquema y host correctos (https en Railway via ProxyFix)
    base_url = request.host_url.rstrip('/')
    # H3: el QR lleva el CÓDIGO PÚBLICO no adivinable (no el id secuencial).
    _codigo = reparacion['codigo_publico']
    if getattr(g, 'taller_slug', None):
        portal_url = f"{base_url}/t/{g.taller_slug}/consulta"
    else:
        portal_url = f"{base_url}/consulta"
    qr_data = f"{portal_url}?codigo={_codigo}"
    qr = QrCodeWidget(qr_data)
    qr.barWidth = 100
    qr.barHeight = 100
    d = Drawing(110, 110)
    d.add(qr)

    # Info table with QR. El CÓDIGO va también en TEXTO (por si no se escanea).
    info_rows = [
        ['Reparación:', f'#{id}'],
        ['Código seguim.:', _codigo or '—'],
        ['Cliente:', reparacion['cliente_nombre']],
        ['Dispositivo:', reparacion['dispositivo']],
        ['Estado:', reparacion['estado']],
        ['Fecha entrada:', reparacion['fecha_entrada'] or '—'],
        ['Precio:', f"{reparacion['precio']:.2f} €" if reparacion['precio'] else 'Pendiente'],
    ]

    info_table = Table(info_rows, colWidths=[3*cm, 7*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2B8AC4')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    # Layout: info left, QR right
    layout = Table([[info_table, d]], colWidths=[10.5*cm, 4*cm])
    layout.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
    ]))
    elements.append(layout)
    elements.append(Spacer(1, 8))

    # Divider line
    divider = Table([['']],colWidths=[page_w - 3*cm])
    divider.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 1, colors.HexColor('#dee2e6')),
    ]))
    elements.append(divider)
    elements.append(Spacer(1, 5))

    # Footer note: instrucción de seguimiento con la URL y el código (para teclear).
    elements.append(Paragraph(
        '<font size="8" color="#6c757d">'
        'Presente este ticket al recoger su dispositivo.<br/>'
        f'<b>Sigue tu reparación en:</b> {portal_url} &nbsp;·&nbsp; '
        f'<b>código:</b> {_codigo} &nbsp;·&nbsp; o escanea el QR.<br/>'
        f'Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")} — '
        f'{" · ".join(filter(None, [_marca["nombre"] or "Taller", _marca["direccion"], _marca["telefono"]]))}'
        '</font>', styles['TKCenter']
    ))

    doc.build(elements)
    buffer.seek(0)

    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f'ticket_recogida_{id}.pdf')


@app.route("/reparaciones/<int:id>/marcar-pagado", methods=["POST"])
@login_required
@csrf_protect
def marcar_reparacion_pagada(id):
    """
    Marca una reparación como pagada.
    Solo accesible por admin y técnicos.
    """
    with get_session() as s:
        rep = s.get(Reparacion, id)

        if not rep:
            flash('❌ Reparación no encontrada.', 'danger')
            return redirect(url_for("reparaciones"))

        # Validar que NO esté ya pagada
        if rep.estado_pago == 'Pagado':
            flash('❌ Esta reparación ya está marcada como pagada.', 'warning')
            return redirect(url_for("editar_reparacion", id=id))

        # Validar que tenga precio
        if not rep.precio or rep.precio <= 0:
            flash('❌ No se puede marcar como pagada: sin presupuesto asignado.', 'danger')
            return redirect(url_for("editar_reparacion", id=id))

        # Obtener datos del formulario
        metodo_pago = request.form.get("metodo_pago", "").strip()

        if not metodo_pago:
            flash('❌ Debe seleccionar un método de pago.', 'danger')
            return redirect(url_for("editar_reparacion", id=id))

        # Actualizar BD
        rep.estado_pago = 'Pagado'
        rep.fecha_pago = datetime.now().strftime("%Y-%m-%d")
        rep.metodo_pago = metodo_pago
        s.commit()
    try:
        logger.info(json.dumps({
            "event": "reparacion_pagada",
            "reparacion_id": id,
            "metodo_pago": metodo_pago,
            "usuario": session.get('usuario')
        }, ensure_ascii=False))
    except Exception:
        logger.info(f"reparacion_pagada id={id} metodo={metodo_pago}")

    flash(f'✅ Pago registrado correctamente ({metodo_pago}).', 'success')
    return redirect(url_for("editar_reparacion", id=id))


# GENERAR PDF PRESUPUESTO
@app.route("/reparaciones/pdf/<int:id>")
@login_required
def generar_pdf_presupuesto(id):
    """
    Genera y descarga un PDF con presupuesto o factura de una reparación.
    Solo accesible por admin y técnicos.
    """
    # Obtener tipo de documento desde parámetro GET (default: presupuesto)
    tipo_documento = request.args.get("tipo", "presupuesto").lower()
    if tipo_documento not in ["presupuesto", "factura"]:
        tipo_documento = "presupuesto"

    with get_session() as s:
        # Obtener reparación y cliente
        reparacion = s.execute(
            select(
                Reparacion.__table__,
                Cliente.nombre.label('cliente_nombre'),
                Cliente.telefono.label('cliente_telefono'),
                Cliente.email.label('cliente_email'),
                Cliente.direccion.label('cliente_direccion'),
            ).outerjoin(Cliente, Cliente.id == Reparacion.cliente_id)
            .where(Reparacion.__table__.c.taller_id == g.taller_id)  # ⚠️ Core → filtro manual
            .where(Reparacion.id == id)
        ).mappings().first()

        if not reparacion:
            flash('Reparación no encontrada.', 'danger')
            return redirect(url_for('reparaciones'))

        # Obtener piezas utilizadas
        piezas = s.execute(
            select(
                PiezaReparacion.cantidad,
                InventarioPieza.nombre,
                InventarioPieza.precio_venta,
            ).join(InventarioPieza, InventarioPieza.id == PiezaReparacion.pieza_id)
            .where(PiezaReparacion.reparacion_id == id)
        ).mappings().all()

    # Convertir fila mapping a dict
    reparacion_data = {
        'id': reparacion['id'],
        'dispositivo': reparacion['dispositivo'],
        'estado': reparacion['estado'],
        'fecha_entrada': reparacion['fecha_entrada'],
        'precio': reparacion['precio'],
        'descripcion': reparacion['descripcion'],
        'cliente_nombre': reparacion['cliente_nombre'],
        'cliente_telefono': reparacion['cliente_telefono'],
        'cliente_email': reparacion['cliente_email'],
        'cliente_direccion': reparacion['cliente_direccion'],
        'codigo_publico': reparacion['codigo_publico'],  # H3: QR por código
        'piezas': [{'nombre': p['nombre'], 'cantidad': p['cantidad'],
                    'precio_venta': p['precio_venta']} for p in piezas],
    }

    # Generar PDF con tipo de documento
    # Pasamos base_url para que el QR apunte al servidor correcto (local o Railway)
    base_url = request.host_url.rstrip('/')
    pdf_buffer = generar_presupuesto_pdf(reparacion_data, tipo_documento=tipo_documento,
                                         base_url=base_url,
                                         taller_slug=getattr(g, 'taller_slug', None),
                                         taller=taller_branding())

    # Retornar como descarga
    nombre_archivo = f"{tipo_documento}_reparacion_{id}.pdf"
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=nombre_archivo
    )

# Dominio admin: ahora en blueprints/admin.py (refactor B1).
from blueprints.admin import bp as admin_bp  # noqa: E402

app.register_blueprint(admin_bp)


@app.route('/publico/pagar/<int:id>', methods=['POST'])
@app.route('/t/<slug>/publico/pagar/<int:id>', methods=['POST'])
@csrf_protect
def publico_pagar(id, slug=None):
    """Endpoint de pago público. Verificación por email antes de crear sesión Stripe."""
    # Fase 2.4 (riesgo 🔴 #2): el pago opera sobre UNA reparación concreta (id).
    # Resolvemos su taller desde el id y fijamos g.taller_id para que el filtro
    # ORM trabaje en el taller correcto y la metadata de Stripe lo lleve. Así un
    # pago jamás puede cruzar de taller.
    from tenancy import _taller_de_reparacion
    _tid_rep = _taller_de_reparacion(id)
    if _tid_rep:
        g.taller_id = _tid_rep

    # 1. Validar email
    cliente_email = request.form.get('cliente_email', '').strip().lower()
    if not cliente_email or '@' not in cliente_email:
        flash('⚠️ Debes proporcionar un correo válido (ej: cliente@ejemplo.com).', 'danger')
        return redirect(url_for('publico.consulta'))

    try:
        with get_session() as s:
            reparacion = s.execute(
                select(
                    Reparacion.id, Reparacion.precio, Reparacion.estado_pago,
                    Cliente.email.label('cliente_email'),
                    Cliente.nombre.label('cliente_nombre'),
                ).join(Cliente, Cliente.id == Reparacion.cliente_id)
                .where(Reparacion.id == id)
            ).mappings().first()
    except Exception:
        logger.exception(json.dumps({"event": "publico_pagar_lookup_error"}, ensure_ascii=False))
        flash('❌ No se pudo completar la operación. Inténtalo de nuevo.', 'danger')
        return redirect(url_for('publico.consulta'))

    # 2. Validar que reparación existe
    if not reparacion:
        flash(f'❌ Reparación #{id} no encontrada en el sistema.', 'danger')
        return redirect(url_for('publico.consulta'))

    # 3. Validar que NO está ya pagada
    if reparacion['estado_pago'] == 'Pagado':
        flash('✅ Esta reparación ya está pagada. No se puede procesar otro pago.', 'info')
        return redirect(url_for('publico.consulta'))

    # 4. Validar precio existe y es > 0
    try:
        precio = float(reparacion['precio']) if reparacion['precio'] else 0
        if precio <= 0:
            flash('❌ No hay un importe válido a pagar para esta reparación.', 'danger')
            return redirect(url_for('publico.consulta'))
    except (ValueError, TypeError):
        flash('❌ Error: el precio no es válido.', 'danger')
        return redirect(url_for('publico.consulta'))

    # 5. Validar email coincide con cliente registrado
    cliente_email_bd = str(reparacion['cliente_email'] or '').strip().lower()
    if not cliente_email_bd:
        flash('❌ El cliente no tiene email registrado. Contacta con administración.', 'danger')
        return redirect(url_for('publico.consulta'))

    if cliente_email != cliente_email_bd:
        flash('❌ El correo no coincide con el cliente registrado para esta reparación.', 'danger')
        return redirect(url_for('publico.consulta'))

    # 6. Validar Stripe configurado
    if not STRIPE_SECRET_KEY or stripe is None:
        flash('⚠️ El sistema de pagos no está configurado. Contacta con el administrador.', 'danger')
        return redirect(url_for('publico.consulta'))
    # si la clave se ve como pública, advertir al usuario/administrador
    if STRIPE_SECRET_KEY.startswith('pk_'):
        logger.warning('Stripe secret key parece una clave pública (pk_...).')
        flash('❌ Clave secreta de Stripe inválida. Verifica las variables de entorno.', 'danger')
        return redirect(url_for('publico.consulta'))

    # 7. Crear sesión Stripe Checkout
    try:
        amount_cents = int(round(precio * 100))
        # obtener nombre de cliente en variable (sqlite3.Row no tiene .get)
        cliente_nombre = reparacion['cliente_nombre'] if reparacion['cliente_nombre'] else ''
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': f"Reparación #{id} - {cliente_nombre or 'Cliente'}"
                    },
                    'unit_amount': amount_cents,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('pago_exito', id=id, _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('publico.consulta', _external=True),
            metadata={
                'reparacion_id': str(id),
                'taller_id': str(g.taller_id),  # Fase 2.4: el webhook lo verifica
                'cliente_email': cliente_email,
                'cliente_nombre': cliente_nombre
            }
        )
        try:
            logger.info(json.dumps({
                "event": "checkout_session_created",
                "reparacion_id": id,
                "session_id": getattr(checkout_session, 'id', None),
                "cliente_email": cliente_email
            }, ensure_ascii=False))
        except Exception:
            logger.info(f"checkout_session_created reparacion={id} cliente={cliente_email}")
        return redirect(checkout_session.url, code=303)
    except stripe.error.CardError as e:
        flash(f'❌ Error de tarjeta: {e.user_message}', 'danger')
        return redirect(url_for('publico.consulta'))
    except stripe.error.RateLimitError:
        flash('❌ Demasiadas solicitudes. Intenta de nuevo en unos momentos.', 'danger')
        return redirect(url_for('publico.consulta'))
    except stripe.error.InvalidRequestError as e:
        flash(f'❌ Error en la solicitud: {e.user_message}', 'danger')
        return redirect(url_for('publico.consulta'))
    except stripe.error.AuthenticationError as e:
        # log masked key and error message for admin debugging
        logger.error(
            "Stripe authentication failed when creating checkout session. "
            "api_key=%s message=%s",
            _mask_key(stripe.api_key) if stripe and getattr(stripe, 'api_key', None) else None,
            str(e.user_message or e)
        )
        flash('❌ Error de autenticación con Stripe. Verifica las claves.', 'danger')
        return redirect(url_for('publico.consulta'))
    except stripe.error.APIConnectionError:
        flash('❌ Error de conexión con Stripe. Intenta de nuevo más tarde.', 'danger')
        return redirect(url_for('publico.consulta'))
    except Exception as e:
        flash('❌ No se pudo iniciar el pago. Inténtalo de nuevo.', 'danger')
        logger.exception(json.dumps({
            "event": "publico_pagar_error",
            "error": str(e)
        }, ensure_ascii=False))
        return redirect(url_for('publico.consulta'))


@app.route('/pago_exito')
def pago_exito():
    # Página de éxito (Stripe redirige aquí con session_id)
    session_id = request.args.get('session_id')
    reparacion_id = request.args.get('id')
    return render_template('pago_exito.html', session_id=session_id, reparacion_id=reparacion_id)


@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    """Webhook de Stripe para procesar eventos de pago."""
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')

    # 1. Validar que webhook secret está configurado
    if not STRIPE_WEBHOOK_SECRET:
        logger.error('[WEBHOOK] ❌ Error: STRIPE_WEBHOOK_SECRET no configurado')
        return jsonify({'error': 'Webhook secret not configured'}), 400

    if not sig_header:
        logger.error('[WEBHOOK] ❌ Error: Stripe-Signature header no encontrado')
        return jsonify({'error': 'Missing Stripe-Signature header'}), 400

    # 2. Verificar la FIRMA del evento. FALLA CERRADO (H4): sin la librería
    # `stripe` no se puede verificar la firma → se RECHAZA (igual que el webhook
    # del SaaS). Nunca se procesa un payload sin verificar.
    if not (stripe and hasattr(stripe, 'Webhook')):
        logger.error('[WEBHOOK] ❌ stripe no disponible: no se puede verificar la firma')
        return jsonify({'error': 'Stripe library unavailable; cannot verify signature'}), 503
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        logger.info(f'[WEBHOOK] ✅ Evento válido: {event.get("type")}')
    except Exception as e:
        logger.error(f'[WEBHOOK] ❌ Firma o payload inválido: {str(e)}')
        return jsonify({'error': str(e)}), 400

    # 3. Procesar evento checkout.session.completed
    if event['type'] == 'checkout.session.completed':
        session_obj = event['data']['object']
        metadata = session_obj.get('metadata', {})
        reparacion_id = metadata.get('reparacion_id')
        meta_taller_id = metadata.get('taller_id')
        cliente_email = metadata.get('cliente_email', 'unknown')
        session_id = session_obj.get('id')

        # Validar metadata
        if not reparacion_id:
            logger.error('[WEBHOOK] ❌ Error: reparacion_id no encontrado en metadata')
            return jsonify({'error': 'Missing reparacion_id in metadata'}), 400

        # Extraer estado/importe reportado por Stripe (si está disponible)
        payment_status = session_obj.get('payment_status') or session_obj.get('status')
        amount_total = None
        # Stripe suele enviar importes en centavos bajo 'amount_total' o 'amount_subtotal'
        if 'amount_total' in session_obj:
            amount_total = session_obj.get('amount_total')
        elif 'amount_subtotal' in session_obj:
            amount_total = session_obj.get('amount_subtotal')

        # Actualizar BD con validaciones adicionales (Fase 1.8: ORM)
        s = None
        try:
            s = get_session()

            # Idempotencia (H6): registra el event_id en el ledger compartido.
            # Si Stripe reenvía el mismo evento, el UNIQUE choca → no se repiten
            # efectos (ni marcar pagado, ni email, ni auditoría duplicada).
            ev_id = event.get('id')
            ins = s.execute(
                insert_or_ignore(StripeEvento)
                .values(event_id=ev_id, tipo=event.get('type'),
                        recibido_en=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                .on_conflict_do_nothing()
            )
            if ev_id and ins.rowcount == 0:
                s.rollback()
                logger.info(json.dumps({"event": "webhook_duplicate",
                                        "stripe_event": ev_id}, ensure_ascii=False))
                return jsonify({'status': 'duplicate'}), 200

            # Verificar que reparación existe
            rep = s.get(Reparacion, reparacion_id)

            if not rep:
                logger.error(json.dumps({
                    "event": "webhook_missing_reparacion",
                    "reparacion_id": reparacion_id,
                    "session_id": session_id
                }, ensure_ascii=False))
                return jsonify({'error': f'Repair #{reparacion_id} not found'}), 404

            # Fase 2.4 (riesgo 🔴 #2): el taller de la metadata DEBE coincidir
            # con el de la reparación. Un pago de un taller jamás puede marcar
            # como pagada una reparación de otro. (El webhook es ruta de
            # plataforma: el ORM no filtra; esta verificación es la barrera.)
            if meta_taller_id is not None and str(rep.taller_id) != str(meta_taller_id):
                logger.error(json.dumps({
                    "event": "webhook_taller_mismatch",
                    "reparacion_id": reparacion_id,
                    "reparacion_taller": rep.taller_id,
                    "metadata_taller": meta_taller_id,
                    "session_id": session_id
                }, ensure_ascii=False))
                return jsonify({'error': 'Taller mismatch'}), 400

            # Verificado: a partir de aquí scopear el resto del webhook al taller
            # de la reparación (auditoría del pago, query email/PDF, slug del QR).
            from tenancy import _slug_por_taller_id
            g.taller_id = rep.taller_id
            g.taller_slug = _slug_por_taller_id(rep.taller_id)

            # Verificar que NO está ya pagada
            if rep.estado_pago == 'Pagado':
                logger.warning(json.dumps({
                    "event": "webhook_already_paid",
                    "reparacion_id": reparacion_id,
                    "session_id": session_id
                }, ensure_ascii=False))
                return jsonify({'status': 'already_paid'}), 200

            # Si Stripe reporta importe y NO coincide con el esperado, NO marcar
            # como pagada (H6): rechaza y deja constancia en audit_log. Un importe
            # distinto del precio del servidor es una anomalía a revisar a mano.
            if amount_total is not None and rep.precio is not None:
                reported = float(amount_total) / 100.0
                expected = float(rep.precio)
                if abs(reported - expected) > 0.01:
                    logger.warning(json.dumps({
                        "event": "webhook_amount_mismatch",
                        "reparacion_id": reparacion_id,
                        "session_id": session_id,
                        "reported_amount": reported,
                        "expected_amount": expected
                    }, ensure_ascii=False))
                    _tid = rep.taller_id
                    s.rollback()
                    registrar_auditoria('pago_importe_no_coincide', None, {
                        'reparacion_id': reparacion_id, 'session_id': session_id,
                        'reported_amount': reported, 'expected_amount': expected,
                    }, ip_address=request.remote_addr, taller_id=_tid)
                    return jsonify({'error': 'Amount mismatch'}), 400

            # Comprobar estado de pago (si está presente)
            if payment_status and str(payment_status).lower() not in ['paid', 'succeeded', 'complete']:
                logger.info(json.dumps({
                    "event": "webhook_payment_not_completed",
                    "reparacion_id": reparacion_id,
                    "session_id": session_id,
                    "payment_status": payment_status
                }, ensure_ascii=False))
                # No marcar como pagada si Stripe no indica pago completado
                return jsonify({'status': 'payment_not_completed'}), 200

            # Marcar como pagada
            rep.estado_pago = 'Pagado'
            rep.fecha_pago = datetime.now().strftime('%Y-%m-%d')
            rep.metodo_pago = 'Tarjeta (Stripe)'
            s.commit()

            # Registrar auditoría y log estructurado
            try:
                registrar_auditoria('pago_registrado', None, {
                    'reparacion_id': reparacion_id,
                    'session_id': session_id,
                    'cliente_email': cliente_email,
                    'amount_reported': amount_total
                }, ip_address=request.remote_addr)
            except Exception:
                logger.exception('Error registrando auditoría de pago')

            # Enviar email de confirmación de pago
            try:
                # Obtener datos completos de la reparación y cliente
                reparacion_data = s.execute(
                    select(
                        Reparacion.__table__,
                        Cliente.nombre, Cliente.email, Cliente.telefono,
                    ).join(Cliente, Reparacion.cliente_id == Cliente.id)
                    # ⚠️ Core → filtro manual; g.taller_id ya es el de la reparación
                    # (fijado tras verificar la metadata más arriba).
                    .where(Reparacion.__table__.c.taller_id == g.taller_id)
                    .where(Reparacion.id == reparacion_id)
                ).mappings().first()

                if reparacion_data:
                    # Generar factura PDF para adjuntar al email
                    pdf_buffer = None
                    try:
                        pdf_reparacion = {
                            'id': reparacion_id,
                            'dispositivo': reparacion_data['dispositivo'],
                            'estado': reparacion_data['estado'],
                            'fecha_entrada': reparacion_data['fecha_entrada'],
                            'precio': reparacion_data['precio'],
                            'descripcion': reparacion_data['descripcion'],
                            'cliente_nombre': reparacion_data['nombre'],
                            'cliente_telefono': reparacion_data['telefono'],
                            'codigo_publico': reparacion_data['codigo_publico'],  # H3
                        }
                        pdf_buffer = generar_presupuesto_pdf(
                            pdf_reparacion, tipo_documento="factura",
                            base_url=request.host_url.rstrip('/'),
                            # El webhook es ruta de plataforma; el slug y los datos
                            # del taller se resuelven desde la metadata de Stripe
                            # (g.taller_id ya es el de la reparación aquí).
                            taller_slug=getattr(g, 'taller_slug', None),
                            taller=taller_branding(),
                        )
                    except Exception:
                        logger.exception(f'[WEBHOOK] Error generando PDF para reparacion {reparacion_id}, se enviara email sin adjunto')

                    # Enviar email de confirmación con factura PDF adjunta
                    notificador.enviar_email("send_payment_confirmation",
                        to_email=reparacion_data['email'],
                        cliente_nombre=reparacion_data['nombre'],
                        reparacion_id=reparacion_id,
                        precio=reparacion_data['precio'],
                        descripcion=reparacion_data['descripcion'],
                        pdf_data=pdf_buffer
                    )
                    logger.info(f'[WEBHOOK] Email de confirmacion enviado a {reparacion_data["email"]} (PDF adjunto: {pdf_buffer is not None})')
                else:
                    logger.warning(f'[WEBHOOK] ⚠️ No se pudieron obtener datos para email de reparación {reparacion_id}')

            except Exception as e:
                logger.exception(f'Error enviando email de confirmación para reparación {reparacion_id}: {str(e)}')

            logger.info(json.dumps({
                "event": "webhook_payment_processed",
                "reparacion_id": reparacion_id,
                "session_id": session_id,
                "cliente_email": cliente_email
            }, ensure_ascii=False))

        except Exception as e:
            logger.error(json.dumps({
                "event": "webhook_update_error",
                "error": str(e),
                "reparacion_id": reparacion_id,
                "session_id": session_id
            }, ensure_ascii=False))
            return jsonify({'error': str(e)}), 500

        finally:
            if s:
                s.close()

    else:
        logger.info(f'[WEBHOOK] ℹ️ Evento no procesado: {event["type"]}')

    return jsonify({'status': 'received'}), 200


# Nota: la ruta /health la define `healthcheck()` en L586 (más rica: timestamp,
# MAIL_CONFIGURED, versión Python). Aquí había un duplicado pobre eliminado en
# pre-fase 0 del SaaS — Flask permitía el doble binding pero solo respondía
# el primero registrado, así que esto era código muerto.

# Global error handlers
@app.errorhandler(403)
def forbidden_error(error):
    try:
        logger.warning(json.dumps({
            "event": "error_403", "path": request.path,
            "usuario": session.get("usuario"), "ip": request.remote_addr
        }, ensure_ascii=False))
    except Exception:
        logger.warning(f"error_403 path={request.path}")
    return render_template('error.html', code=403,
                           message='No tienes permiso para acceder a esto.'), 403


@app.errorhandler(404)
def not_found_error(error):
    try:
        logger.warning(json.dumps({
            "event": "error_404",
            "path": request.path,
            "ip": request.remote_addr
        }, ensure_ascii=False))
    except Exception:
        logger.warning(f"error_404 path={request.path}")
    return render_template('error.html', code=404, message='Página no encontrada'), 404


@app.errorhandler(500)
def internal_error(error):
    try:
        logger.exception(json.dumps({
            "event": "error_500",
            "path": request.path,
            "error": str(error)
        }, ensure_ascii=False))
    except Exception:
        logger.exception('error_500')
    return render_template('error.html', code=500, message='Error interno del servidor'), 500

# =========================================
# 🔸 FUNCIÓN PARA CREAR USUARIO ADMIN INICIAL
# =========================================
# Descomenta y ejecuta esta función UNA VEZ para crear el usuario admin
# Luego vuelve a comentarla para evitar recrearlo
# def crear_admin_inicial():
#     with get_session() as s:  # (actualizado en Fase 1.9; antes usaba sqlite3)
#     hashed_password = generate_password_hash("admin123")  # Cambia la contraseña
#     try:
#         conn.execute("""
#             INSERT INTO usuarios (usuario, contraseña, rol)
#             VALUES (?, ?, ?)
#         """, ("admin", hashed_password, "admin"))
#         conn.commit()
#         print("Usuario admin creado exitosamente.")
#     except sqlite3.IntegrityError:
#         print("El usuario admin ya existe.")
#     conn.close()

# Para ejecutar: descomenta la línea siguiente y corre el script
# crear_admin_inicial()

#  EJECUCIÓN
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
