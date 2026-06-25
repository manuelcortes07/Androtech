import json
import logging
import os
import secrets
import socket
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
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
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

# Suscripción del SaaS (Fase 3b) — flujo Stripe SEPARADO del de reparaciones.
import saas_billing
from alerts import calcular_alertas_reparacion
from audit import crear_tabla_auditoria, obtener_auditoria_reciente
from auth import (
    init_permisos_db,
    login_required,
    tiene_permiso,
)

# local modules (split responsibilities)
from branding import taller_branding
from database import get_engine, get_session, is_postgres

# Paginación clásica numerada (B5).
from utils.security import (
    ensure_csrf_token,
    inject_csrf_token,
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
    "auth.login", "auth.logout", "suscripcion.signup",
    # Facturación: un taller bloqueado DEBE poder llegar a pagar/gestionar
    "suscripcion.suscripcion", "suscripcion.suscripcion_portal",
    "suscripcion.suscripcion_bloqueado",
    # Webhooks (sin sesión, pero exentos por claridad)
    "suscripcion.saas_webhook", "pagos.stripe_webhook",
    "static", "health",
    # Portal público del taller: SIEMPRE visible (decisión de producto) — un
    # taller bloqueado no perjudica a sus clientes finales.
    "publico.consulta", "publico.mis_reparaciones", "publico.solicitar_reparacion",
    "pagos.publico_pagar", "pagos.pago_exito",
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
        return redirect(url_for("suscripcion.suscripcion_bloqueado"))


app.before_request(puerta_suscripcion)

# Exponer el taller activo a las plantillas (para construir URLs /t/{slug}/...).
@app.context_processor
def inject_taller():
    # `marca` = datos del taller activo para el escaparate público y los pies
    # (plano (b) del rebranding). Degrada a defaults si no hay taller resuelto.
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
# Dominio reparaciones: ahora en blueprints/reparaciones.py (refactor B1).
from blueprints.reparaciones import bp as reparaciones_bp  # noqa: E402
from query_helpers import (  # noqa: E402, F401
    _ultimas_actualizaciones,
    build_reparaciones_filters,
)

app.register_blueprint(reparaciones_bp)

# Dominios inventario y admin (sus registros estaban interleados con las rutas
# de reparaciones; se reubican aquí tras el slice — refactor B1).
from blueprints.admin import bp as admin_bp  # noqa: E402
from blueprints.inventario import bp as inventario_bp  # noqa: E402

app.register_blueprint(inventario_bp)
app.register_blueprint(admin_bp)


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
_CSRF_EXENTAS = frozenset({"pagos.stripe_webhook", "suscripcion.saas_webhook"})


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
# Dominio suscripción del SaaS (signup + facturación + webhook): ahora en
# blueprints/suscripcion.py (refactor B1). Flujo Stripe del SaaS (StripeClient
# dedicado), SEPARADO del pago de reparaciones. La PUERTA puerta_suscripcion
# (before_request) se queda en app.py; sus exenciones usan suscripcion.* abajo.
from blueprints.suscripcion import bp as suscripcion_bp  # noqa: E402

app.register_blueprint(suscripcion_bp)

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


# Helpers de exportación CSV: extraídos a csv_utils.py (refactor B1).


# Dominio facturación/pagos de reparaciones: ahora en blueprints/pagos.py
# (refactor B1). Flujo Stripe de reparaciones (api_key global), SEPARADO del
# de la suscripción del SaaS. El webhook /stripe/webhook queda CSRF-exento por
# _CSRF_EXENTAS abajo (pagos.stripe_webhook).
from blueprints.pagos import bp as pagos_bp  # noqa: E402

app.register_blueprint(pagos_bp)


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
