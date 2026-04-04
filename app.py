from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
import os
from datetime import datetime, timedelta
import secrets
import logging
import json
import urllib.parse
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

try:
    import stripe
except ImportError:
    stripe = None
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail

# local modules (split responsibilities)
from utils.pdf_generator import generar_presupuesto_pdf
from db import get_db
from auth import login_required, role_required
from alerts import calcular_alertas_reparacion
from historial import registrar_cambio_estado, validar_transicion
from audit import registrar_auditoria, obtener_auditoria_reciente, crear_tabla_auditoria
from utils.security import (
    ensure_csrf_token,
    inject_csrf_token,
    csrf_protect,
    validar_precio,
    validar_contraseña,
)
from utils.email_service import EmailService

app = Flask(__name__)
# Secret key should be provided via environment variable in production
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_urlsafe(32))
# Configure session expiration
app.permanent_session_lifetime = timedelta(hours=6)  # ajustable según política

# Ensure sessions are permanent by default
@app.before_request
def make_session_permanent():
    session.permanent = True

@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
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

logger.setLevel(logging.INFO)

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

# Inicializar tabla de auditoría
_conn_init = get_db()
crear_tabla_auditoria(_conn_init)

# Inicializar tabla de fotos de reparaciones
_conn_init.execute("""
    CREATE TABLE IF NOT EXISTS fotos_reparacion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reparacion_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        descripcion TEXT,
        fecha_subida TEXT NOT NULL,
        subido_por TEXT,
        FOREIGN KEY (reparacion_id) REFERENCES reparaciones(id) ON DELETE CASCADE
    )
""")
# Añadir columna firma si no existe
try:
    _conn_init.execute("ALTER TABLE reparaciones ADD COLUMN firma TEXT")
    _conn_init.commit()
except Exception:
    pass  # columna ya existe

# Tabla de notas internas
_conn_init.execute("""
    CREATE TABLE IF NOT EXISTS notas_reparacion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reparacion_id INTEGER NOT NULL,
        usuario TEXT NOT NULL,
        contenido TEXT NOT NULL,
        fecha_creacion TEXT NOT NULL,
        es_importante INTEGER DEFAULT 0,
        FOREIGN KEY (reparacion_id) REFERENCES reparaciones(id) ON DELETE CASCADE
    )
""")
_conn_init.commit()

# Tabla de inventario de piezas
_conn_init.execute("""
    CREATE TABLE IF NOT EXISTS inventario_piezas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        categoria TEXT DEFAULT 'General',
        descripcion TEXT,
        cantidad INTEGER DEFAULT 0,
        cantidad_minima INTEGER DEFAULT 5,
        precio_coste REAL DEFAULT 0,
        precio_venta REAL DEFAULT 0,
        proveedor TEXT,
        ubicacion TEXT,
        fecha_actualizacion TEXT
    )
""")

# Tabla de piezas usadas en reparaciones
_conn_init.execute("""
    CREATE TABLE IF NOT EXISTS piezas_reparacion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reparacion_id INTEGER NOT NULL,
        pieza_id INTEGER NOT NULL,
        cantidad INTEGER DEFAULT 1,
        fecha_uso TEXT NOT NULL,
        usuario TEXT,
        FOREIGN KEY (reparacion_id) REFERENCES reparaciones(id),
        FOREIGN KEY (pieza_id) REFERENCES inventario_piezas(id)
    )
""")
_conn_init.commit()
_conn_init.close()

# Configuración de subida de fotos
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'reparaciones')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
SIGNATURES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'firmas')
os.makedirs(SIGNATURES_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB por archivo
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB total por request


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Flask-Mail configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@androtech.com')
app.config['MAIL_DEFAULT_CHARSET'] = 'utf-8'
app.config['MAIL_DEFAULT_CONTENT_TYPE'] = 'text/html'
app.config['MAIL_SUPPRESS_SEND'] = False

mail = Mail(app)
email_service = EmailService(mail)

# register CSRF helpers from utils/security
app.before_request(ensure_csrf_token)
app.context_processor(inject_csrf_token)

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
        except:
            return date_str
    else:
        date_obj = date_str
    return date_obj.strftime(format_str)


# -------------------------
# Helpers: filters builder
# -------------------------
def build_reparaciones_filters(args):
    """Construye cláusula WHERE y parámetros a partir de query params.

    args: objeto parecido a dict (p. ej. request.args)
    Devuelve (where_clause, params_list)
    """
    clauses = []
    params = []

    cliente = args.get('cliente')
    if cliente:
        clauses.append("clientes.nombre LIKE ?")
        params.append(f"%{cliente}%")

    estado = args.get('estado')
    if estado:
        clauses.append("reparaciones.estado = ?")
        params.append(estado)

    pago = args.get('pago')
    if pago:
        clauses.append("reparaciones.estado_pago = ?")
        params.append(pago)

    fecha_desde = args.get('fecha_desde')
    if fecha_desde:
        clauses.append("reparaciones.fecha_entrada >= ?")
        params.append(fecha_desde)

    fecha_hasta = args.get('fecha_hasta')
    if fecha_hasta:
        clauses.append("reparaciones.fecha_entrada <= ?")
        params.append(fecha_hasta)

    where = " AND ".join(clauses) if clauses else "1=1"
    return where, params


# ==============================
# Endpoint: Export reparaciones
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

    conn = get_db()
    query = (
        "SELECT reparaciones.id, clientes.nombre as cliente, clientes.telefono, "
        "reparaciones.dispositivo, reparaciones.estado, reparaciones.estado_pago, "
        "reparaciones.precio, reparaciones.fecha_entrada, reparaciones.fecha_pago as fecha_finalizacion "
        "FROM reparaciones JOIN clientes ON clientes.id = reparaciones.cliente_id "
        f"WHERE {where} ORDER BY reparaciones.id DESC"
    )

    rows = conn.execute(query, params).fetchall()

    import csv
    from io import StringIO
    from flask import Response

    output = StringIO()
    writer = csv.writer(output)

    # Header
    header = [
        'ID', 'Cliente', 'Teléfono', 'Dispositivo', 'Estado', 'Estado pago',
        'Precio', 'Fecha entrada', 'Fecha finalización', 'Días en taller', 'Alertas'
    ]
    writer.writerow(header)

    for r in rows:
        rdict = dict(r)
        fecha_entrada = rdict.get('fecha_entrada')
        fecha_fin = rdict.get('fecha_finalizacion')

        # calcular dias en taller
        dias = ''
        try:
            if fecha_entrada:
                fmt = '%Y-%m-%d'
                from datetime import datetime
                d_ent = datetime.strptime(fecha_entrada, fmt)
                if fecha_fin:
                    d_fin = datetime.strptime(fecha_fin, fmt)
                else:
                    d_fin = datetime.now()
                dias = (d_fin - d_ent).days
        except Exception:
            dias = ''

        # alertas en texto plano
        alertas_txt = ''
        try:
            alert_info = calcular_alertas_reparacion(rdict)
            if alert_info and alert_info.get('tiene_alertas'):
                alertas_txt = '; '.join([a['mensaje'] for a in alert_info['alertas']])
        except Exception:
            alertas_txt = ''

        writer.writerow([
            rdict.get('id'), rdict.get('cliente'), rdict.get('telefono'),
            rdict.get('dispositivo'), rdict.get('estado'), rdict.get('estado_pago'),
            rdict.get('precio'), fecha_entrada, fecha_fin, dias, alertas_txt
        ])

    conn.close()
    output.seek(0)
    filename = f"reparaciones_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(output.getvalue(), mimetype='text/csv', headers={
        'Content-Disposition': f'attachment;filename={filename}'
    })



# CSRF PROTECCIÓN (simple token en sesión)
@app.before_request
def ensure_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(16)

@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=session.get('csrf_token'))


def validate_csrf():
    token = request.form.get('csrf_token', '')
    if not token or token != session.get('csrf_token'):
        flash('Formulario inválido o expirado. Intenta de nuevo.', 'danger')
        return False
    return True


# ``csrf_protect`` now imported from utils/security; definition
# removed from this module.


# Database connection function now lives in db.py and is
# imported as ``get_db``. Keeping this placeholder comment for clarity.

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

# LOGIN
@app.route("/login", methods=["GET", "POST"])
@csrf_protect
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        contraseña = request.form["contraseña"]

        conn = get_db()
        user = conn.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()

        if user and check_password_hash(user["contraseña"], contraseña):
            session["usuario"] = user["usuario"]
            session["rol"] = user["rol"]
            flash(f"Bienvenido, {user['usuario']}!", "success")
            
            # Registrar auditoría
            registrar_auditoria(conn, 'login', user['usuario'], {
                'rol': user['rol'],
                'ip': request.remote_addr
            }, ip_address=request.remote_addr)
            
            try:
                logger.info(json.dumps({
                    "event": "login_success",
                    "user": user['usuario'],
                    "role": user['rol'],
                    "ip": request.remote_addr
                }, ensure_ascii=False))
            except Exception:
                logger.info(f"login_success user={user['usuario']}")
            
            conn.close()
            return redirect(url_for("dashboard"))
        else:
            flash("Usuario o contraseña incorrectos.", "danger")
            
            # Registrar intento fallido
            registrar_auditoria(conn, 'login_failed', usuario or 'unknown', {
                'ip': request.remote_addr
            }, ip_address=request.remote_addr)
            
            try:
                logger.warning(json.dumps({
                    "event": "login_failed",
                    "user": usuario,
                    "ip": request.remote_addr
                }, ensure_ascii=False))
            except Exception:
                logger.warning(f"login_failed user={usuario}")
            
            conn.close()

    return render_template("login.html")

# LOGOUT
@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("Has cerrado sesión correctamente.", "info")
    return redirect(url_for("login"))

# =========================================
# 🔸 PÁGINAS PROTEGIDAS
# =========================================

# PÁGINA PRINCIPAL
@app.route("/")
def index():
    conn = get_db()
    total_clientes = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    activas = conn.execute("SELECT COUNT(*) FROM reparaciones WHERE estado != 'Terminado' AND estado != 'Entregado'").fetchone()[0]
    terminadas = conn.execute("SELECT COUNT(*) FROM reparaciones WHERE estado = 'Terminado' OR estado = 'Entregado'").fetchone()[0]
    ingresos = conn.execute("SELECT COALESCE(SUM(precio), 0) FROM reparaciones WHERE estado = 'Terminado' OR estado = 'Entregado'").fetchone()[0]
    # Desglose por estado para mini-panel del hero
    estados_count = {}
    for row in conn.execute("SELECT estado, COUNT(*) as c FROM reparaciones GROUP BY estado").fetchall():
        estados_count[row['estado']] = row['c']
    conn.close()
    return render_template("index.html",
        total_clientes=total_clientes,
        activas=activas,
        terminadas=terminadas,
        ingresos=ingresos,
        estados_count=estados_count
    )

# =========================================
# 🔸 DASHBOARD
# =========================================

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    
    # ========== ESTADÍSTICAS GENERALES ==========
    total_clientes = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    total_reparaciones = conn.execute("SELECT COUNT(*) FROM reparaciones").fetchone()[0]
    
    reparaciones_activas = conn.execute("""
        SELECT COUNT(*) FROM reparaciones
        WHERE estado != 'Terminado' AND estado != 'Entregado'
    """).fetchone()[0]
    
    reparaciones_terminadas = conn.execute("""
        SELECT COUNT(*) FROM reparaciones
        WHERE estado = 'Terminado' OR estado = 'Entregado'
    """).fetchone()[0]
    
    # Ingresos totales
    ingresos_total = conn.execute("""
        SELECT IFNULL(SUM(precio), 0) FROM reparaciones
        WHERE precio IS NOT NULL
    """).fetchone()[0]
    
    # ========== ESTADÍSTICAS DE ESTE MES ==========
    hoy = datetime.now()
    inicio_mes = datetime(hoy.year, hoy.month, 1)
    
    ingresos_mes = conn.execute("""
        SELECT IFNULL(SUM(precio), 0) FROM reparaciones
        WHERE fecha_entrada >= ? AND precio IS NOT NULL
    """, (inicio_mes.strftime("%Y-%m-%d"),)).fetchone()[0]
    
    reparaciones_mes = conn.execute("""
        SELECT COUNT(*) FROM reparaciones
        WHERE fecha_entrada >= ?
    """, (inicio_mes.strftime("%Y-%m-%d"),)).fetchone()[0]
    
    reparaciones_completadas_mes = conn.execute("""
        SELECT COUNT(*) FROM reparaciones
        WHERE (estado = 'Terminado' OR estado = 'Entregado')
        AND fecha_entrada >= ?
    """, (inicio_mes.strftime("%Y-%m-%d"),)).fetchone()[0]
    
    # ========== ESTADÍSTICAS DE PAGOS ==========
    dinero_cobrado = conn.execute("""
        SELECT IFNULL(SUM(precio), 0) FROM reparaciones
        WHERE estado_pago = 'Pagado' AND precio IS NOT NULL
    """).fetchone()[0]
    
    dinero_por_cobrar = ingresos_total - dinero_cobrado
    
    reparaciones_pendiente_pago = conn.execute("""
        SELECT COUNT(*) FROM reparaciones
        WHERE estado_pago = 'Pendiente' AND precio IS NOT NULL AND precio > 0
    """).fetchone()[0]
    
    reparaciones_pagadas = conn.execute("""
        SELECT COUNT(*) FROM reparaciones
        WHERE estado_pago = 'Pagado'
    """).fetchone()[0]
    
    # Calcular tasa de cobro (porcentaje)
    tasa_cobro = 0
    if ingresos_total > 0:
        tasa_cobro = round((dinero_cobrado / ingresos_total * 100), 1)
    
    # Obtener reparaciones pendientes de pago (últimas 5)
    reparaciones_sin_pagar = conn.execute("""
        SELECT reparaciones.*, clientes.nombre AS cliente
        FROM reparaciones
        LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id
        WHERE reparaciones.estado_pago = 'Pendiente' 
        AND reparaciones.precio IS NOT NULL AND reparaciones.precio > 0
        ORDER BY reparaciones.id DESC
        LIMIT 5
    """).fetchall()
    reparaciones_sin_pagar_list = [dict(r) for r in reparaciones_sin_pagar] if reparaciones_sin_pagar else []
    
    # ========== DISPOSITIVOS MÁS REPARADOS ==========
    dispositivos_top = conn.execute("""
        SELECT dispositivo, COUNT(*) as cantidad
        FROM reparaciones
        WHERE dispositivo IS NOT NULL AND dispositivo != ''
        GROUP BY dispositivo
        ORDER BY cantidad DESC
        LIMIT 5
    """).fetchall()
    
    # ========== ESTADOS MÁS COMUNES ==========
    estados_distribucion = conn.execute("""
        SELECT estado, COUNT(*) as cantidad
        FROM reparaciones
        GROUP BY estado
        ORDER BY cantidad DESC
    """).fetchall()
    
    # Convertir a dict para template
    dispositivos_dict = [{"nombre": d[0], "cantidad": d[1]} for d in dispositivos_top] if dispositivos_top else []
    estados_dict = [{"nombre": e[0], "cantidad": e[1]} for e in estados_distribucion] if estados_distribucion else []
    
    # Calcular porcentajes
    total_rep = reparaciones_activas + reparaciones_terminadas
    porcentaje_activas = round((reparaciones_activas / total_rep * 100), 1) if total_rep > 0 else 0
    porcentaje_terminadas = round((reparaciones_terminadas / total_rep * 100), 1) if total_rep > 0 else 0
    
    # Últimas 5 reparaciones
    ultimas_reparaciones = conn.execute("""
        SELECT reparaciones.*, clientes.nombre AS cliente
        FROM reparaciones
        LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id
        ORDER BY reparaciones.id DESC
        LIMIT 5
    """).fetchall()
    
    # ========== REPARACIONES ATRASADAS (sin actualización hace > 7 días) ==========
    hace_7_dias = (hoy - __import__('datetime').timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    
    reparaciones_atrasadas = conn.execute("""
        SELECT reparaciones.*, clientes.nombre AS cliente,
               (SELECT fecha_cambio FROM reparaciones_historial 
                WHERE reparacion_id = reparaciones.id 
                ORDER BY fecha_cambio DESC LIMIT 1) AS ultima_actualizacion
        FROM reparaciones
        LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id
        WHERE reparaciones.estado IN ('En proceso', 'Pendiente')
        AND (
            SELECT fecha_cambio FROM reparaciones_historial 
            WHERE reparacion_id = reparaciones.id 
            ORDER BY fecha_cambio DESC LIMIT 1
        ) < ? 
        OR (
            SELECT COUNT(*) FROM reparaciones_historial 
            WHERE reparacion_id = reparaciones.id
        ) = 0
        ORDER BY reparaciones.id DESC
    """, (hace_7_dias,)).fetchall()
    
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
        
        ingreso_mes_i = conn.execute("""
            SELECT IFNULL(SUM(precio), 0) FROM reparaciones
            WHERE fecha_entrada >= ? AND fecha_entrada <= ? AND precio IS NOT NULL
        """, (inicio.strftime("%Y-%m-%d"), fin.strftime("%Y-%m-%d"))).fetchone()[0]
        
        ingresos_por_mes.append({
            "mes": inicio.strftime("%b %Y"),
            "valor": round(ingreso_mes_i, 2)
        })
    
    # ========== MÉTRICA 2: TIEMPO MEDIO DE REPARACIÓN ==========
    tiempo_medio_dias = 0
    reparaciones_completadas = conn.execute("""
        SELECT COUNT(*) FROM reparaciones
        WHERE estado = 'Terminado' OR estado = 'Entregado'
    """).fetchone()[0]
    
    if reparaciones_completadas > 0:
        # Calcular promedio de días entre entrada y última actualización
        tiempo_promedio = conn.execute("""
            SELECT AVG(
                CAST((julianday(COALESCE(
                    (SELECT fecha_cambio FROM reparaciones_historial 
                     WHERE reparacion_id = reparaciones.id 
                     ORDER BY fecha_cambio DESC LIMIT 1),
                    reparaciones.fecha_entrada
                )) - julianday(reparaciones.fecha_entrada)) AS REAL)
            )
            FROM reparaciones
            WHERE estado = 'Terminado' OR estado = 'Entregado'
        """).fetchone()[0]
        
        if tiempo_promedio:
            tiempo_medio_dias = round(float(tiempo_promedio), 1)
    
    # ========== MÉTRICA 3: REPARACIONES POR TÉCNICO ==========
    reparaciones_por_tecnico = conn.execute("""
        SELECT usuario, COUNT(*) as cantidad
        FROM reparaciones_historial
        WHERE usuario IS NOT NULL AND usuario != ''
        GROUP BY usuario
        ORDER BY cantidad DESC
    """).fetchall()
    
    tecnico_dict = [{"nombre": t[0], "cantidad": t[1]} for t in reparaciones_por_tecnico] if reparaciones_por_tecnico else []
    
    # ========== AUDITORÍA RECIENTE (últimos 10 eventos) ==========
    eventos_auditoria = obtener_auditoria_reciente(conn, limite=10)
    
    conn.close()
    
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
@app.route("/clientes")
@login_required
def clientes():
    conn = get_db()
    clientes = conn.execute("SELECT * FROM clientes").fetchall()
    conn.close()
    return render_template("clientes.html", clientes=clientes)


# CREAR CLIENTE
@app.route("/clientes/nuevo", methods=["GET", "POST"])
@login_required
@csrf_protect
def nuevo_cliente():
    if request.method == "POST":
        nombre = request.form["nombre"]
        telefono = request.form["telefono"]
        email = request.form["email"]
        direccion = request.form["direccion"]

        conn = get_db()
        conn.execute("""
            INSERT INTO clientes (nombre, telefono, email, direccion)
            VALUES (?, ?, ?, ?)
        """, (nombre, telefono, email, direccion))
        conn.commit()
        conn.close()

        # Enviar email de bienvenida al nuevo cliente
        if email:
            try:
                email_service.send_bienvenida_cliente(
                    to_email=email,
                    cliente_nombre=nombre
                )
                logger.info(f"Email de bienvenida enviado a {email} para cliente {nombre}")
            except Exception as e:
                logger.error(f"Error enviando email de bienvenida: {type(e).__name__}: {str(e)}")

        return redirect(url_for("clientes"))

    return render_template("nuevo_cliente.html")


# EDITAR CLIENTE
@app.route("/clientes/editar/<int:id>", methods=["GET", "POST"])
@login_required
@csrf_protect
def editar_cliente(id):
    conn = get_db()

    if request.method == "POST":
        nombre = request.form["nombre"]
        telefono = request.form["telefono"]
        email = request.form["email"]
        direccion = request.form["direccion"]

        conn.execute("""
            UPDATE clientes
            SET nombre=?, telefono=?, email=?, direccion=?
            WHERE id=?
        """, (nombre, telefono, email, direccion, id))
        conn.commit()
        conn.close()

        return redirect(url_for("clientes"))

    cliente = conn.execute("SELECT * FROM clientes WHERE id=?", (id,)).fetchone()
    conn.close()

    return render_template("editar_cliente.html", cliente=cliente)


# HISTORIAL CLIENTE - SOLO ADMIN
@app.route("/cliente/historial")
@role_required('admin')
def historial_cliente():
    conn = get_db()

    # Estadísticas generales
    total_reparaciones = conn.execute("SELECT COUNT(*) FROM reparaciones").fetchone()[0]
    pagadas = conn.execute("SELECT COUNT(*) FROM reparaciones WHERE estado_pago = 'Pagado'").fetchone()[0]
    pendientes = conn.execute("SELECT COUNT(*) FROM reparaciones WHERE estado_pago != 'Pagado'").fetchone()[0]
    total_invertido = conn.execute("SELECT IFNULL(SUM(precio), 0) FROM reparaciones WHERE precio IS NOT NULL").fetchone()[0]
    promedio_precio = conn.execute("SELECT IFNULL(AVG(precio), 0) FROM reparaciones WHERE precio IS NOT NULL").fetchone()[0]
    total_completadas = conn.execute("SELECT COUNT(*) FROM reparaciones WHERE estado = 'Terminado' OR estado = 'Entregado'").fetchone()[0]

    # Filtro por estado y cliente
    estado_filtro = request.args.get('estado', '').strip()
    cliente_filtro = request.args.get('cliente_id', '').strip()

    # Paginación
    try:
        page = int(request.args.get('page', 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1
    per_page = 10
    offset = (page - 1) * per_page

    base_sql = "SELECT reparaciones.*, clientes.nombre AS cliente FROM reparaciones LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id"
    where = []
    params = []
    if estado_filtro:
        where.append("reparaciones.estado = ?")
        params.append(estado_filtro)
    if cliente_filtro:
        where.append("reparaciones.cliente_id = ?")
        params.append(cliente_filtro)

    where_clause = (" WHERE " + " AND ".join(where)) if where else ""

    total_count = conn.execute("SELECT COUNT(*) FROM reparaciones" + where_clause, params).fetchone()[0]
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

    reparaciones_rows = conn.execute(base_sql + where_clause + " ORDER BY reparaciones.id DESC LIMIT ? OFFSET ?", params + [per_page, offset]).fetchall()
    reparaciones = [dict(r) for r in reparaciones_rows]

    # Enriquecer datos con última actualización de cada reparación
    reparaciones_enriquecidas = []
    for r in reparaciones:
        # Obtener última actualización del historial
        ultima_actualizacion = conn.execute(
            "SELECT fecha_cambio FROM reparaciones_historial WHERE reparacion_id = ? ORDER BY fecha_cambio DESC LIMIT 1",
            (r['id'],)
        ).fetchone()
        r['ultima_actualizacion'] = ultima_actualizacion['fecha_cambio'] if ultima_actualizacion else None
        reparaciones_enriquecidas.append(r)

    estados = conn.execute("SELECT DISTINCT estado FROM reparaciones ORDER BY estado").fetchall()
    clientes = conn.execute("SELECT id, nombre FROM clientes ORDER BY nombre").fetchall()

    conn.close()

    stats = {
        'total_reparaciones': total_reparaciones,
        'pagadas': pagadas,
        'pendientes': pendientes,
        'total_invertido': total_invertido or 0,
        'promedio_precio': promedio_precio or 0,
        'total_completadas': total_completadas,
    }

    return render_template('historial_cliente.html', reparaciones=reparaciones_enriquecidas, stats=stats, estados=estados, clientes=clientes, estado_filtro=estado_filtro, cliente_filtro=cliente_filtro, page=page, total_pages=total_pages)


# EXPORTAR PDF HISTORIAL CLIENTE
@app.route("/cliente/<int:id>/historial-pdf")
@login_required
def exportar_historial_cliente_pdf(id):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from io import BytesIO

    conn = get_db()
    cliente = conn.execute("SELECT * FROM clientes WHERE id=?", (id,)).fetchone()
    if not cliente:
        conn.close()
        flash('Cliente no encontrado.', 'danger')
        return redirect(url_for('clientes'))

    reparaciones = conn.execute("""
        SELECT * FROM reparaciones WHERE cliente_id=? ORDER BY fecha_entrada DESC
    """, (id,)).fetchall()
    conn.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ATTitle', parent=styles['Heading1'], fontSize=22,
                               textColor=colors.HexColor('#2B8AC4'), alignment=TA_CENTER, spaceAfter=5))
    styles.add(ParagraphStyle(name='ATSub', parent=styles['Normal'], fontSize=10,
                               textColor=colors.HexColor('#6c757d'), alignment=TA_CENTER, spaceAfter=20))
    styles.add(ParagraphStyle(name='ATSection', parent=styles['Heading2'], fontSize=13,
                               textColor=colors.HexColor('#0F1923'), spaceAfter=10))

    elements = []

    # Header
    elements.append(Paragraph("AndroTech", styles['ATTitle']))
    elements.append(Paragraph("Historial de Reparaciones del Cliente", styles['ATSub']))

    # Client info
    elements.append(Paragraph("Datos del Cliente", styles['ATSection']))
    info_data = [
        ['Nombre:', cliente['nombre']],
        ['Email:', cliente['email'] or '—'],
        ['Teléfono:', cliente['telefono'] or '—'],
        ['Dirección:', cliente['direccion'] or '—'],
    ]
    info_table = Table(info_data, colWidths=[3.5*cm, 13*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2B8AC4')),
        ('LINEBELOW', (0, -1), (-1, -1), 1, colors.HexColor('#dee2e6')),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 15))

    # Stats
    total = len(reparaciones)
    total_pagado = sum(r['precio'] or 0 for r in reparaciones if r['estado_pago'] == 'Pagado')
    completadas = sum(1 for r in reparaciones if r['estado'] in ('Terminado', 'Entregado'))
    elements.append(Paragraph("Resumen", styles['ATSection']))
    stats_data = [
        ['Total Reparaciones', 'Completadas', 'Total Pagado'],
        [str(total), str(completadas), f"{total_pagado:.2f} €"]
    ]
    stats_table = Table(stats_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2B8AC4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#EBF5FB')),
    ]))
    elements.append(stats_table)
    elements.append(Spacer(1, 15))

    # Repairs table
    if reparaciones:
        elements.append(Paragraph("Detalle de Reparaciones", styles['ATSection']))
        headers = ['#', 'Dispositivo', 'Estado', 'Precio', 'Pago', 'Fecha']
        table_data = [headers]
        for r in reparaciones:
            table_data.append([
                str(r['id']),
                str(r['dispositivo'])[:30],
                r['estado'],
                f"{r['precio']:.2f} €" if r['precio'] else '—',
                r['estado_pago'] or 'Pendiente',
                r['fecha_entrada'] or '—'
            ])

        rep_table = Table(table_data, colWidths=[1.2*cm, 5.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm])
        rep_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2B8AC4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ]))
        elements.append(rep_table)

    elements.append(Spacer(1, 25))
    elements.append(Paragraph(
        f'<para alignment="center"><font size="8" color="#9ba5b0">'
        f'Generado el {datetime.now().strftime("%d/%m/%Y %H:%M")} — AndroTech, Huelva | +34 633 234 395'
        f'</font></para>', styles['Normal']
    ))

    doc.build(elements)
    buffer.seek(0)

    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f'historial_{cliente["nombre"].replace(" ", "_")}_{datetime.now().strftime("%Y%m%d")}.pdf')


# BORRAR CLIENTE
@app.route("/clientes/borrar/<int:id>")
@role_required('admin')
def borrar_cliente(id):
    conn = get_db()
    conn.execute("DELETE FROM clientes WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("clientes"))


# =========================================
#  🔸 BÚSQUEDA GLOBAL
# =========================================

@app.route("/buscar")
@login_required
def buscar():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        flash('Introduce al menos 2 caracteres para buscar.', 'warning')
        return redirect(url_for('dashboard'))

    conn = get_db()
    like = f'%{q}%'

    clientes_result = conn.execute('''
        SELECT id, nombre, email, telefono
        FROM clientes
        WHERE nombre LIKE ? OR email LIKE ? OR telefono LIKE ?
        LIMIT 20
    ''', (like, like, like)).fetchall()

    reparaciones_result = conn.execute('''
        SELECT r.id, r.dispositivo, r.estado, r.estado_pago, r.precio,
               r.fecha_entrada, c.nombre as cliente
        FROM reparaciones r
        JOIN clientes c ON r.cliente_id = c.id
        WHERE r.dispositivo LIKE ? OR r.descripcion LIKE ?
              OR c.nombre LIKE ? OR CAST(r.id AS TEXT) = ?
        ORDER BY r.id DESC
        LIMIT 20
    ''', (like, like, like, q)).fetchall()

    conn.close()

    return render_template("buscar.html",
        q=q,
        clientes=clientes_result,
        reparaciones=reparaciones_result
    )


# =========================================
#  🔸 EXPORTAR CSV
# =========================================

import csv
from io import StringIO, BytesIO

@app.route("/exportar/reparaciones.csv")
@login_required
@role_required('admin')
def exportar_reparaciones_csv():
    conn = get_db()
    rows = conn.execute('''
        SELECT r.id, c.nombre as cliente, c.email, c.telefono, c.direccion,
               r.dispositivo, r.descripcion, r.estado, r.estado_pago,
               r.precio, r.fecha_entrada, r.fecha_salida, r.fecha_pago, r.metodo_pago,
               r.tipo_documento,
               (SELECT COUNT(*) FROM fotos_reparacion WHERE reparacion_id = r.id) as num_fotos,
               (SELECT COUNT(*) FROM notas_reparacion WHERE reparacion_id = r.id) as num_notas,
               CASE WHEN r.firma IS NOT NULL AND r.firma != '' THEN 'Si' ELSE 'No' END as firmado
        FROM reparaciones r
        LEFT JOIN clientes c ON r.cliente_id = c.id
        ORDER BY r.id DESC
    ''').fetchall()

    # Estadisticas resumen
    total = len(rows)
    total_facturado = sum(r['precio'] or 0 for r in rows)
    total_pagado = sum(r['precio'] or 0 for r in rows if r['estado_pago'] == 'Pagado')
    total_pendiente = total_facturado - total_pagado
    conn.close()

    si = StringIO()
    writer = csv.writer(si, delimiter=';')

    # Cabecera del informe
    writer.writerow(['INFORME DE REPARACIONES - ANDROTECH'])
    writer.writerow([f'Fecha de exportacion: {datetime.now().strftime("%d/%m/%Y %H:%M")}'])
    writer.writerow([f'Total registros: {total}'])
    writer.writerow([f'Total facturado: {total_facturado:.2f} EUR'])
    writer.writerow([f'Total cobrado: {total_pagado:.2f} EUR'])
    writer.writerow([f'Pendiente de cobro: {total_pendiente:.2f} EUR'])
    writer.writerow([])

    # Cabeceras de columnas
    writer.writerow(['N. Reparacion', 'Cliente', 'Email', 'Telefono', 'Direccion',
                     'Dispositivo', 'Descripcion', 'Estado', 'Estado Pago',
                     'Precio (EUR)', 'Tipo Documento', 'Fecha Entrada', 'Fecha Salida',
                     'Fecha Pago', 'Metodo Pago', 'Fotos', 'Notas', 'Firmado'])

    for r in rows:
        precio_fmt = f'{r["precio"]:.2f}'.replace('.', ',') if r['precio'] else '0,00'
        writer.writerow([
            r['id'], r['cliente'] or 'Sin asignar', r['email'] or '', r['telefono'] or '',
            r['direccion'] or '', r['dispositivo'], r['descripcion'] or '',
            r['estado'], r['estado_pago'], precio_fmt, r['tipo_documento'] or '',
            r['fecha_entrada'] or '', r['fecha_salida'] or '',
            r['fecha_pago'] or '', r['metodo_pago'] or '',
            r['num_fotos'], r['num_notas'], r['firmado']
        ])

    output = BytesIO()
    output.write(si.getvalue().encode('utf-8-sig'))
    output.seek(0)
    return send_file(output, mimetype='text/csv', as_attachment=True,
                     download_name=f'AndroTech_Reparaciones_{datetime.now().strftime("%Y%m%d")}.csv')


@app.route("/exportar/clientes.csv")
@login_required
@role_required('admin')
def exportar_clientes_csv():
    conn = get_db()
    rows = conn.execute('''
        SELECT c.id, c.nombre, c.email, c.telefono, c.direccion,
               COUNT(r.id) as total_reparaciones,
               SUM(CASE WHEN r.estado IN ('Pendiente', 'En proceso') THEN 1 ELSE 0 END) as reparaciones_activas,
               SUM(CASE WHEN r.estado IN ('Terminado', 'Entregado') THEN 1 ELSE 0 END) as reparaciones_completadas,
               COALESCE(SUM(r.precio), 0) as total_facturado,
               COALESCE(SUM(CASE WHEN r.estado_pago = 'Pagado' THEN r.precio ELSE 0 END), 0) as total_pagado,
               COALESCE(SUM(CASE WHEN r.estado_pago = 'Pendiente' THEN r.precio ELSE 0 END), 0) as total_pendiente,
               MAX(r.fecha_entrada) as ultima_visita
        FROM clientes c
        LEFT JOIN reparaciones r ON r.cliente_id = c.id
        GROUP BY c.id
        ORDER BY c.nombre
    ''').fetchall()

    total_clientes = len(rows)
    total_facturado = sum(r['total_facturado'] or 0 for r in rows)
    total_cobrado = sum(r['total_pagado'] or 0 for r in rows)
    conn.close()

    si = StringIO()
    writer = csv.writer(si, delimiter=';')

    # Cabecera del informe
    writer.writerow(['INFORME DE CLIENTES - ANDROTECH'])
    writer.writerow([f'Fecha de exportacion: {datetime.now().strftime("%d/%m/%Y %H:%M")}'])
    writer.writerow([f'Total clientes: {total_clientes}'])
    writer.writerow([f'Total facturado: {total_facturado:.2f} EUR'])
    writer.writerow([f'Total cobrado: {total_cobrado:.2f} EUR'])
    writer.writerow([])

    # Cabeceras de columnas
    writer.writerow(['N. Cliente', 'Nombre', 'Email', 'Telefono', 'Direccion',
                     'Total Reparaciones', 'Activas', 'Completadas',
                     'Total Facturado (EUR)', 'Total Pagado (EUR)', 'Pendiente (EUR)',
                     'Ultima Visita'])

    for r in rows:
        facturado_fmt = f'{r["total_facturado"]:.2f}'.replace('.', ',')
        pagado_fmt = f'{r["total_pagado"]:.2f}'.replace('.', ',')
        pendiente_fmt = f'{r["total_pendiente"]:.2f}'.replace('.', ',')
        writer.writerow([
            r['id'], r['nombre'], r['email'] or '', r['telefono'] or '',
            r['direccion'] or '', r['total_reparaciones'],
            r['reparaciones_activas'] or 0, r['reparaciones_completadas'] or 0,
            facturado_fmt, pagado_fmt, pendiente_fmt,
            r['ultima_visita'] or 'Sin visitas'
        ])

    output = BytesIO()
    output.write(si.getvalue().encode('utf-8-sig'))
    output.seek(0)
    return send_file(output, mimetype='text/csv', as_attachment=True,
                     download_name=f'AndroTech_Clientes_{datetime.now().strftime("%Y%m%d")}.csv')


# =========================================
#  🔸 SECCIÓN REPARACIONES
# =========================================

# LISTAR REPARACIONES
@app.route("/reparaciones")
@login_required
def reparaciones():
    conn = get_db()

    # Recoger filtros desde query string
    cliente_id = request.args.get('cliente_id', '').strip()
    estado = request.args.get('estado', '').strip()
    desde = request.args.get('desde', '').strip()
    hasta = request.args.get('hasta', '').strip()
    precio_min = request.args.get('precio_min', '').strip()
    precio_max = request.args.get('precio_max', '').strip()
    # búsqueda global
    q = request.args.get('q', '').strip()

    # Paginación
    try:
        page = int(request.args.get('page', 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1
    per_page = 10
    offset = (page - 1) * per_page

    sql_base = "FROM reparaciones LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id"

    where_clauses = []
    params = []

    if cliente_id:
        where_clauses.append("reparaciones.cliente_id = ?")
        params.append(cliente_id)

    if estado:
        where_clauses.append("reparaciones.estado = ?")
        params.append(estado)

    if q:
        q_clauses = []
        # buscar por ID exacta si es numérico
        try:
            q_id = int(q)
            q_clauses.append("reparaciones.id = ?")
            params.append(q_id)
        except ValueError:
            pass
        q_clauses.append("clientes.nombre LIKE ?")
        params.append(f"%{q}%")
        q_clauses.append("clientes.telefono LIKE ?")
        params.append(f"%{q}%")
        where_clauses.append("(" + " OR ".join(q_clauses) + ")")

    if desde:
        where_clauses.append("reparaciones.fecha_entrada >= ?")
        params.append(desde)

    if hasta:
        where_clauses.append("reparaciones.fecha_entrada <= ?")
        params.append(hasta)

    if precio_min:
        try:
            params.append(float(precio_min))
            where_clauses.append("reparaciones.precio >= ?")
        except ValueError:
            pass

    if precio_max:
        try:
            params.append(float(precio_max))
            where_clauses.append("reparaciones.precio <= ?")
        except ValueError:
            pass

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Total para paginación
    total_sql = "SELECT COUNT(*) " + sql_base + where_sql
    total = conn.execute(total_sql, tuple(params)).fetchone()[0]

    # Consulta principal con orden y límite
    select_sql = "SELECT reparaciones.*, clientes.nombre AS cliente " + sql_base + where_sql + " ORDER BY fecha_entrada DESC LIMIT ? OFFSET ?"
    final_params = params + [per_page, offset]
    datos = conn.execute(select_sql, tuple(final_params)).fetchall()

    # Enriquecer datos con última actualización de cada reparación
    datos_enriquecidos = []
    for r in datos:
        r_dict = dict(r)
        # Obtener última actualización del historial
        ultima_actualizacion = conn.execute(
            "SELECT fecha_cambio FROM reparaciones_historial WHERE reparacion_id = ? ORDER BY fecha_cambio DESC LIMIT 1",
            (r_dict['id'],)
        ).fetchone()
        r_dict['ultima_actualizacion'] = ultima_actualizacion['fecha_cambio'] if ultima_actualizacion else None
        
        # Calcular alertas inteligentes
        r_dict['alertas_info'] = calcular_alertas_reparacion(r_dict, r_dict['ultima_actualizacion'])
        
        datos_enriquecidos.append(r_dict)

    # Lista de clientes para filtro
    clientes = conn.execute("SELECT id, nombre FROM clientes ORDER BY nombre").fetchall()

    conn.close()

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

    total_pages = max(1, (total + per_page - 1) // per_page)

    # Determinar si mostrar precios según rol
    mostrar_precios = session.get('rol') in ['admin', 'tecnico']

    return render_template("reparaciones.html", reparaciones=datos_enriquecidos, clientes=clientes, filters=filters, filters_query=filters_query, page=page, total_pages=total_pages, per_page=per_page, total=total, mostrar_precios=mostrar_precios, user_role=session.get('rol'))


# NUEVA REPARACIÓN
@app.route("/reparaciones/nueva", methods=["GET", "POST"])
@login_required
@csrf_protect
def nueva_reparacion():
    conn = get_db()

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
                conn.close()
                return redirect(url_for('nueva_reparacion'))
            if session.get('rol') != 'admin':
                precio = None
            else:
                precio = float(precio)
        else:
            precio = None

        cur = conn.execute("""
            INSERT INTO reparaciones (cliente_id, dispositivo, descripcion, estado, fecha_entrada, precio)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (cliente_id, dispositivo, descripcion, estado, fecha_entrada, precio))
        conn.commit()
        new_id = getattr(cur, 'lastrowid', None)

        # Guardar fotos subidas
        fotos = request.files.getlist('fotos')
        for foto in fotos:
            if foto and foto.filename and allowed_file(foto.filename):
                ext = foto.filename.rsplit('.', 1)[1].lower()
                unique_name = f"{new_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}.{ext}"
                foto.save(os.path.join(UPLOAD_FOLDER, unique_name))
                conn.execute(
                    "INSERT INTO fotos_reparacion (reparacion_id, filename, descripcion, fecha_subida, subido_por) VALUES (?, ?, ?, ?, ?)",
                    (new_id, unique_name, '', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session.get('usuario'))
                )
        conn.commit()

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
            cliente = conn.execute("SELECT nombre, email FROM clientes WHERE id=?", (cliente_id,)).fetchone()
            if cliente and cliente['email']:
                email_service.send_nueva_reparacion(
                    to_email=cliente['email'],
                    cliente_nombre=cliente['nombre'],
                    reparacion_id=new_id,
                    dispositivo=dispositivo,
                    descripcion=descripcion,
                    fecha_entrada=fecha_entrada
                )
                logger.info(f"Email de nueva reparacion enviado para reparacion {new_id}")
        except Exception as e:
            logger.error(f"Error enviando email de nueva reparacion: {type(e).__name__}: {str(e)}")

        conn.close()
        return redirect(url_for("reparaciones"))

    clientes = conn.execute("SELECT * FROM clientes").fetchall()
    conn.close()

    return render_template("nueva_reparacion.html", clientes=clientes)


# EDITAR REPARACIÓN
@app.route("/reparaciones/editar/<int:id>", methods=["GET", "POST"])
@login_required
@csrf_protect
def editar_reparacion(id):
    conn = get_db()

    if request.method == "POST":
        cliente_id = request.form["cliente_id"]
        dispositivo = request.form["dispositivo"]
        descripcion = request.form["descripcion"]
        estado = request.form["estado"]
        precio = request.form["precio"]

        # Validar transición de estado
        estado_anterior = conn.execute("SELECT estado FROM reparaciones WHERE id=?", (id,)).fetchone()['estado']
        transicion_valida, error_transicion = validar_transicion(
            estado_anterior, estado, rol=session.get('rol', 'tecnico')
        )
        if not transicion_valida:
            flash(error_transicion, 'danger')
            conn.close()
            return redirect(url_for('editar_reparacion', id=id))

        # precio validación: solo admin puede cambiar precio
        if precio:
            if not validar_precio(precio):
                flash('Precio inválido', 'danger')
                conn.close()
                return redirect(url_for('editar_reparacion', id=id))
            precio_val = float(precio)
            if session.get('rol') != 'admin':
                # si no es admin, no permitimos alterar precio
                original = conn.execute("SELECT precio FROM reparaciones WHERE id=?", (id,)).fetchone()['precio']
                precio = original
            else:
                precio = precio_val
        else:
            precio = None

        # Registrar cambio de estado en historial (ANTES de actualizar)
        registrar_cambio_estado(conn, id, estado, usuario=session.get('usuario'))

        conn.execute("""
            UPDATE reparaciones
            SET cliente_id=?, dispositivo=?, descripcion=?, estado=?, precio=?
            WHERE id=?
        """, (cliente_id, dispositivo, descripcion, estado, precio, id))

        conn.commit()

        # Enviar email de actualización de estado si cambió
        if estado_anterior != estado:
            try:
                # Obtener datos del cliente para el email
                cliente_data = conn.execute('''
                    SELECT c.nombre, c.email
                    FROM reparaciones r
                    JOIN clientes c ON r.cliente_id = c.id
                    WHERE r.id = ?
                ''', (id,)).fetchone()

                if cliente_data and cliente_data['email']:
                    # Enviar email de actualización de estado
                    email_service.send_repair_status_update(
                        to_email=cliente_data['email'],
                        cliente_nombre=cliente_data['nombre'],
                        reparacion_id=id,
                        estado_anterior=estado_anterior,
                        estado_nuevo=estado,
                        dispositivo=dispositivo,
                        descripcion=descripcion
                    )
                    logger.info(f'[EMAIL] Email de actualizacion de estado enviado a {cliente_data["email"]} para reparacion {id}')
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
        conn.close()
        return redirect(url_for("reparaciones"))

    reparacion = conn.execute("SELECT * FROM reparaciones WHERE id=?", (id,)).fetchone()
    clientes = conn.execute("SELECT * FROM clientes").fetchall()

    # Historial completo de estados para timeline
    historial_rows = conn.execute(
        "SELECT estado_anterior, estado_nuevo, fecha_cambio, usuario "
        "FROM reparaciones_historial WHERE reparacion_id = ? "
        "ORDER BY fecha_cambio ASC",
        (id,)
    ).fetchall()
    historial = [dict(h) for h in historial_rows] if historial_rows else []

    # Obtener fotos de la reparación
    fotos_rows = conn.execute(
        "SELECT * FROM fotos_reparacion WHERE reparacion_id = ? ORDER BY fecha_subida DESC",
        (id,)
    ).fetchall()
    fotos = [dict(f) for f in fotos_rows] if fotos_rows else []

    # Obtener notas internas
    notas_rows = conn.execute(
        "SELECT * FROM notas_reparacion WHERE reparacion_id = ? ORDER BY fecha_creacion DESC",
        (id,)
    ).fetchall()
    notas = [dict(n) for n in notas_rows] if notas_rows else []

    # Obtener piezas usadas en esta reparación
    piezas_rows = conn.execute("""
        SELECT pr.*, ip.nombre as pieza_nombre, ip.precio_venta
        FROM piezas_reparacion pr
        JOIN inventario_piezas ip ON pr.pieza_id = ip.id
        WHERE pr.reparacion_id = ?
        ORDER BY pr.fecha_uso DESC
    """, (id,)).fetchall()
    piezas_usadas = [dict(p) for p in piezas_rows] if piezas_rows else []

    # Obtener última actualización para calcular alertas
    ultima_actualizacion = conn.execute(
        "SELECT fecha_cambio FROM reparaciones_historial WHERE reparacion_id = ? ORDER BY fecha_cambio DESC LIMIT 1",
        (id,)
    ).fetchone()
    ultima_act = ultima_actualizacion['fecha_cambio'] if ultima_actualizacion else None

    conn.close()

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
@role_required('admin')
def borrar_reparacion(id):
    conn = get_db()
    
    # Validar que no esté pagada
    reparacion = conn.execute("SELECT estado_pago FROM reparaciones WHERE id=?", (id,)).fetchone()
    if reparacion and reparacion['estado_pago'] == 'Pagado':
        conn.close()
        flash('❌ No se puede eliminar: esta reparación ya está pagada.', 'danger')
        return redirect(url_for("reparaciones"))
    
    # Eliminar fotos asociadas
    fotos = conn.execute("SELECT filename FROM fotos_reparacion WHERE reparacion_id=?", (id,)).fetchall()
    for foto in fotos:
        filepath = os.path.join(UPLOAD_FOLDER, foto['filename'])
        if os.path.exists(filepath):
            os.remove(filepath)
    conn.execute("DELETE FROM fotos_reparacion WHERE reparacion_id=?", (id,))

    conn.execute("DELETE FROM reparaciones WHERE id=?", (id,))
    conn.commit()
    try:
        logger.info(json.dumps({
            "event": "reparacion_deleted",
            "reparacion_id": id,
            "usuario": session.get('usuario')
        }, ensure_ascii=False))
    except Exception:
        logger.info(f"reparacion_deleted id={id}")
    conn.close()
    flash('✅ Reparación eliminada correctamente.', 'success')
    return redirect(url_for("reparaciones"))


# SUBIR FOTOS A REPARACIÓN
@app.route("/reparaciones/<int:id>/fotos", methods=["POST"])
@login_required
def subir_fotos_reparacion(id):
    conn = get_db()
    reparacion = conn.execute("SELECT id FROM reparaciones WHERE id=?", (id,)).fetchone()
    if not reparacion:
        conn.close()
        flash('Reparación no encontrada.', 'danger')
        return redirect(url_for('reparaciones'))

    fotos = request.files.getlist('fotos')
    count = 0
    for foto in fotos:
        if foto and foto.filename and allowed_file(foto.filename):
            ext = foto.filename.rsplit('.', 1)[1].lower()
            unique_name = f"{id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}.{ext}"
            foto.save(os.path.join(UPLOAD_FOLDER, unique_name))
            conn.execute(
                "INSERT INTO fotos_reparacion (reparacion_id, filename, descripcion, fecha_subida, subido_por) VALUES (?, ?, ?, ?, ?)",
                (id, unique_name, '', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session.get('usuario'))
            )
            count += 1

    conn.commit()
    conn.close()
    if count:
        flash(f'Se subieron {count} foto(s) correctamente.', 'success')
    else:
        flash('No se subieron fotos. Formatos permitidos: PNG, JPG, JPEG, WebP, GIF (max 5MB).', 'warning')
    return redirect(url_for('editar_reparacion', id=id))


# ELIMINAR FOTO DE REPARACIÓN
@app.route("/reparaciones/fotos/<int:foto_id>/eliminar", methods=["POST"])
@login_required
def eliminar_foto_reparacion(foto_id):
    conn = get_db()
    foto = conn.execute("SELECT * FROM fotos_reparacion WHERE id=?", (foto_id,)).fetchone()
    if not foto:
        conn.close()
        flash('Foto no encontrada.', 'danger')
        return redirect(url_for('reparaciones'))

    reparacion_id = foto['reparacion_id']

    # Eliminar archivo físico
    filepath = os.path.join(UPLOAD_FOLDER, foto['filename'])
    if os.path.exists(filepath):
        os.remove(filepath)

    conn.execute("DELETE FROM fotos_reparacion WHERE id=?", (foto_id,))
    conn.commit()
    conn.close()
    flash('Foto eliminada correctamente.', 'success')
    return redirect(url_for('editar_reparacion', id=reparacion_id))


# FIRMA DIGITAL DEL CLIENTE
@app.route("/reparaciones/<int:id>/firma", methods=["GET"])
@login_required
def firmar_reparacion(id):
    conn = get_db()
    reparacion = conn.execute(
        "SELECT r.*, c.nombre as cliente_nombre FROM reparaciones r JOIN clientes c ON r.cliente_id = c.id WHERE r.id=?",
        (id,)
    ).fetchone()
    if not reparacion:
        conn.close()
        flash('Reparación no encontrada.', 'danger')
        return redirect(url_for('reparaciones'))
    conn.close()
    return render_template("firmar_reparacion.html", reparacion=reparacion)


@app.route("/reparaciones/<int:id>/firma", methods=["POST"])
@login_required
def guardar_firma_reparacion(id):
    import base64
    # CSRF check for JSON requests
    csrf_token = request.headers.get('X-CSRFToken', '')
    if not csrf_token or csrf_token != session.get('csrf_token'):
        return jsonify({"error": "Token CSRF inválido"}), 403

    conn = get_db()
    reparacion = conn.execute("SELECT id, firma FROM reparaciones WHERE id=?", (id,)).fetchone()
    if not reparacion:
        conn.close()
        return jsonify({"error": "Reparación no encontrada"}), 404

    data = request.get_json()
    if not data or not data.get('firma'):
        conn.close()
        return jsonify({"error": "No se recibió la firma"}), 400

    # Decodificar base64 PNG
    firma_data = data['firma']
    if ',' in firma_data:
        firma_data = firma_data.split(',')[1]

    try:
        img_bytes = base64.b64decode(firma_data)
    except Exception:
        conn.close()
        return jsonify({"error": "Datos de firma inválidos"}), 400

    # Eliminar firma anterior si existe
    if reparacion['firma']:
        old_path = os.path.join(SIGNATURES_FOLDER, reparacion['firma'])
        if os.path.exists(old_path):
            os.remove(old_path)

    # Guardar nueva firma
    filename = f"firma_{id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
    filepath = os.path.join(SIGNATURES_FOLDER, filename)
    with open(filepath, 'wb') as f:
        f.write(img_bytes)

    conn.execute("UPDATE reparaciones SET firma=? WHERE id=?", (filename, id))
    conn.commit()
    conn.close()

    logger.info(f"firma_guardada reparacion_id={id} usuario={session.get('usuario')}")
    return jsonify({"success": True, "filename": filename})


# NOTAS INTERNAS DE REPARACIÓN
@app.route("/reparaciones/<int:id>/notas", methods=["POST"])
@login_required
@csrf_protect
def agregar_nota_reparacion(id):
    conn = get_db()
    reparacion = conn.execute("SELECT id FROM reparaciones WHERE id=?", (id,)).fetchone()
    if not reparacion:
        conn.close()
        flash('Reparación no encontrada.', 'danger')
        return redirect(url_for('reparaciones'))

    contenido = request.form.get('contenido', '').strip()
    if not contenido:
        conn.close()
        flash('La nota no puede estar vacía.', 'warning')
        return redirect(url_for('editar_reparacion', id=id))

    es_importante = 1 if request.form.get('es_importante') else 0

    conn.execute(
        "INSERT INTO notas_reparacion (reparacion_id, usuario, contenido, fecha_creacion, es_importante) VALUES (?, ?, ?, ?, ?)",
        (id, session.get('usuario'), contenido, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), es_importante)
    )
    conn.commit()
    conn.close()
    flash('Nota agregada correctamente.', 'success')
    return redirect(url_for('editar_reparacion', id=id))


@app.route("/reparaciones/notas/<int:nota_id>/eliminar", methods=["POST"])
@login_required
@csrf_protect
def eliminar_nota_reparacion(nota_id):
    conn = get_db()
    nota = conn.execute("SELECT * FROM notas_reparacion WHERE id=?", (nota_id,)).fetchone()
    if not nota:
        conn.close()
        flash('Nota no encontrada.', 'danger')
        return redirect(url_for('reparaciones'))

    reparacion_id = nota['reparacion_id']
    # Solo el autor o admin pueden eliminar
    if nota['usuario'] != session.get('usuario') and session.get('rol') != 'admin':
        conn.close()
        flash('No tienes permiso para eliminar esta nota.', 'danger')
        return redirect(url_for('editar_reparacion', id=reparacion_id))

    conn.execute("DELETE FROM notas_reparacion WHERE id=?", (nota_id,))
    conn.commit()
    conn.close()
    flash('Nota eliminada.', 'success')
    return redirect(url_for('editar_reparacion', id=reparacion_id))


# ── INVENTARIO DE PIEZAS ──────────────────────────────────────────

@app.route("/inventario")
@role_required('admin')
def inventario():
    conn = get_db()
    buscar = request.args.get('q', '').strip()
    categoria = request.args.get('categoria', '').strip()

    query = "SELECT * FROM inventario_piezas WHERE 1=1"
    params = []
    if buscar:
        query += " AND (nombre LIKE ? OR proveedor LIKE ?)"
        params += [f"%{buscar}%", f"%{buscar}%"]
    if categoria:
        query += " AND categoria = ?"
        params.append(categoria)
    query += " ORDER BY nombre ASC"

    piezas = conn.execute(query, params).fetchall()

    # KPIs
    total = len(piezas)
    stock_bajo = sum(1 for p in piezas if p['cantidad'] <= p['cantidad_minima'])
    valor_total = sum((p['precio_coste'] or 0) * (p['cantidad'] or 0) for p in piezas)

    conn.close()
    return render_template("inventario.html", piezas=piezas, total=total,
                           stock_bajo=stock_bajo, valor_total=valor_total,
                           buscar=buscar, categoria=categoria)


@app.route("/inventario/nueva", methods=["GET", "POST"])
@role_required('admin')
@csrf_protect
def nueva_pieza():
    if request.method == "POST":
        conn = get_db()
        conn.execute("""
            INSERT INTO inventario_piezas (nombre, categoria, descripcion, cantidad, cantidad_minima,
                                           precio_coste, precio_venta, proveedor, ubicacion, fecha_actualizacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form['nombre'],
            request.form.get('categoria', 'General'),
            request.form.get('descripcion', ''),
            int(request.form.get('cantidad', 0)),
            int(request.form.get('cantidad_minima', 5)),
            float(request.form.get('precio_coste', 0) or 0),
            float(request.form.get('precio_venta', 0) or 0),
            request.form.get('proveedor', ''),
            request.form.get('ubicacion', ''),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        conn.commit()
        conn.close()
        flash('Pieza añadida al inventario.', 'success')
        return redirect(url_for('inventario'))
    return render_template("nueva_pieza.html")


@app.route("/inventario/editar/<int:id>", methods=["GET", "POST"])
@role_required('admin')
@csrf_protect
def editar_pieza(id):
    conn = get_db()
    if request.method == "POST":
        conn.execute("""
            UPDATE inventario_piezas
            SET nombre=?, categoria=?, descripcion=?, cantidad=?, cantidad_minima=?,
                precio_coste=?, precio_venta=?, proveedor=?, ubicacion=?, fecha_actualizacion=?
            WHERE id=?
        """, (
            request.form['nombre'],
            request.form.get('categoria', 'General'),
            request.form.get('descripcion', ''),
            int(request.form.get('cantidad', 0)),
            int(request.form.get('cantidad_minima', 5)),
            float(request.form.get('precio_coste', 0) or 0),
            float(request.form.get('precio_venta', 0) or 0),
            request.form.get('proveedor', ''),
            request.form.get('ubicacion', ''),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            id
        ))
        conn.commit()
        conn.close()
        flash('Pieza actualizada.', 'success')
        return redirect(url_for('inventario'))

    pieza = conn.execute("SELECT * FROM inventario_piezas WHERE id=?", (id,)).fetchone()
    conn.close()
    if not pieza:
        flash('Pieza no encontrada.', 'danger')
        return redirect(url_for('inventario'))
    return render_template("editar_pieza.html", pieza=pieza)


@app.route("/inventario/eliminar/<int:id>")
@role_required('admin')
def eliminar_pieza(id):
    conn = get_db()
    en_uso = conn.execute("SELECT COUNT(*) as c FROM piezas_reparacion WHERE pieza_id=?", (id,)).fetchone()['c']
    if en_uso > 0:
        conn.close()
        flash(f'No se puede eliminar: esta pieza está asociada a {en_uso} reparación(es).', 'danger')
        return redirect(url_for('inventario'))
    conn.execute("DELETE FROM inventario_piezas WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('Pieza eliminada del inventario.', 'success')
    return redirect(url_for('inventario'))


@app.route("/api/inventario/buscar")
@login_required
def api_buscar_piezas():
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])
    conn = get_db()
    rows = conn.execute(
        "SELECT id, nombre, cantidad, precio_venta FROM inventario_piezas WHERE nombre LIKE ? LIMIT 10",
        (f"%{q}%",)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/reparaciones/<int:id>/piezas", methods=["POST"])
@login_required
@csrf_protect
def agregar_pieza_reparacion(id):
    conn = get_db()
    pieza_id = int(request.form['pieza_id'])
    cantidad = int(request.form.get('cantidad', 1))

    pieza = conn.execute("SELECT * FROM inventario_piezas WHERE id=?", (pieza_id,)).fetchone()
    if not pieza:
        conn.close()
        flash('Pieza no encontrada.', 'danger')
        return redirect(url_for('editar_reparacion', id=id))

    if pieza['cantidad'] < cantidad:
        conn.close()
        flash(f'Stock insuficiente. Disponible: {pieza["cantidad"]}', 'warning')
        return redirect(url_for('editar_reparacion', id=id))

    conn.execute(
        "INSERT INTO piezas_reparacion (reparacion_id, pieza_id, cantidad, fecha_uso, usuario) VALUES (?, ?, ?, ?, ?)",
        (id, pieza_id, cantidad, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session.get('usuario'))
    )
    conn.execute("UPDATE inventario_piezas SET cantidad = cantidad - ?, fecha_actualizacion = ? WHERE id = ?",
                 (cantidad, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), pieza_id))
    conn.commit()
    conn.close()
    flash(f'Pieza "{pieza["nombre"]}" x{cantidad} añadida a la reparación.', 'success')
    return redirect(url_for('editar_reparacion', id=id))


@app.route("/reparaciones/piezas/<int:uso_id>/eliminar", methods=["POST"])
@login_required
@csrf_protect
def eliminar_pieza_reparacion(uso_id):
    conn = get_db()
    uso = conn.execute("SELECT * FROM piezas_reparacion WHERE id=?", (uso_id,)).fetchone()
    if not uso:
        conn.close()
        flash('Registro no encontrado.', 'danger')
        return redirect(url_for('reparaciones'))

    reparacion_id = uso['reparacion_id']
    # Restaurar stock
    conn.execute("UPDATE inventario_piezas SET cantidad = cantidad + ?, fecha_actualizacion = ? WHERE id = ?",
                 (uso['cantidad'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'), uso['pieza_id']))
    conn.execute("DELETE FROM piezas_reparacion WHERE id=?", (uso_id,))
    conn.commit()
    conn.close()
    flash('Pieza devuelta al inventario.', 'success')
    return redirect(url_for('editar_reparacion', id=reparacion_id))


# ── CALENDARIO DE REPARACIONES ─────────────────────────────────────

@app.route("/calendario")
@login_required
def calendario():
    return render_template("calendario.html")


@app.route("/api/calendario/eventos")
@login_required
def api_calendario_eventos():
    conn = get_db()
    rows = conn.execute("""
        SELECT r.id, r.dispositivo, r.estado, r.fecha_entrada, r.fecha_salida,
               c.nombre as cliente
        FROM reparaciones r
        JOIN clientes c ON r.cliente_id = c.id
    """).fetchall()
    conn.close()

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
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from io import BytesIO

    conn = get_db()
    reparacion = conn.execute("""
        SELECT r.*, c.nombre as cliente_nombre, c.telefono as cliente_telefono, c.email as cliente_email
        FROM reparaciones r
        JOIN clientes c ON r.cliente_id = c.id
        WHERE r.id = ?
    """, (id,)).fetchone()
    conn.close()

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

    # Header
    elements.append(Paragraph("AndroTech", styles['TKTitle']))
    elements.append(Paragraph("TICKET DE RECOGIDA", styles['TKSub']))

    # QR code with repair ID
    qr_data = f"ANDROTECH-REP-{id}"
    qr = QrCodeWidget(qr_data)
    qr.barWidth = 100
    qr.barHeight = 100
    d = Drawing(110, 110)
    d.add(qr)

    # Info table with QR
    info_rows = [
        ['Reparación:', f'#{id}'],
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

    # Footer note
    elements.append(Paragraph(
        '<font size="8" color="#6c757d">'
        'Presente este ticket al recoger su dispositivo. '
        'El código QR será escaneado para verificar la entrega.<br/>'
        f'Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")} — AndroTech, Huelva — +34 633 234 395'
        '</font>', styles['TKCenter']
    ))

    doc.build(elements)
    buffer.seek(0)

    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f'ticket_recogida_{id}.pdf')


@app.route("/reparaciones/<int:id>/marcar-pagado", methods=["POST"])
@login_required
def marcar_reparacion_pagada(id):
    """
    Marca una reparación como pagada.
    Solo accesible por admin y técnicos.
    """
    conn = get_db()
    
    # Obtener reparación
    reparacion = conn.execute("SELECT * FROM reparaciones WHERE id=?", (id,)).fetchone()
    
    if not reparacion:
        conn.close()
        flash('❌ Reparación no encontrada.', 'danger')
        return redirect(url_for("reparaciones"))
    
    # Validar que NO esté ya pagada
    if reparacion['estado_pago'] == 'Pagado':
        conn.close()
        flash('❌ Esta reparación ya está marcada como pagada.', 'warning')
        return redirect(url_for("editar_reparacion", id=id))
    
    # Validar que tenga precio
    if not reparacion['precio'] or reparacion['precio'] <= 0:
        conn.close()
        flash('❌ No se puede marcar como pagada: sin presupuesto asignado.', 'danger')
        return redirect(url_for("editar_reparacion", id=id))
    
    # Obtener datos del formulario
    metodo_pago = request.form.get("metodo_pago", "").strip()
    
    if not metodo_pago:
        conn.close()
        flash('❌ Debe seleccionar un método de pago.', 'danger')
        return redirect(url_for("editar_reparacion", id=id))
    
    # Actualizar BD
    fecha_pago = datetime.now().strftime("%Y-%m-%d")
    conn.execute("""
        UPDATE reparaciones 
        SET estado_pago='Pagado', fecha_pago=?, metodo_pago=?
        WHERE id=?
    """, (fecha_pago, metodo_pago, id))
    conn.commit()
    try:
        logger.info(json.dumps({
            "event": "reparacion_pagada",
            "reparacion_id": id,
            "metodo_pago": metodo_pago,
            "usuario": session.get('usuario')
        }, ensure_ascii=False))
    except Exception:
        logger.info(f"reparacion_pagada id={id} metodo={metodo_pago}")
    conn.close()
    
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
    
    conn = get_db()
    
    # Obtener reparación y cliente
    reparacion = conn.execute("""
        SELECT r.*, c.nombre AS cliente_nombre, c.telefono AS cliente_telefono,
               c.email AS cliente_email, c.direccion AS cliente_direccion
        FROM reparaciones r
        LEFT JOIN clientes c ON c.id = r.cliente_id
        WHERE r.id = ?
    """, (id,)).fetchone()

    if not reparacion:
        conn.close()
        flash('Reparación no encontrada.', 'danger')
        return redirect(url_for('reparaciones'))

    # Obtener piezas utilizadas
    piezas = conn.execute("""
        SELECT pr.cantidad, ip.nombre, ip.precio_venta
        FROM piezas_reparacion pr
        JOIN inventario_piezas ip ON ip.id = pr.pieza_id
        WHERE pr.reparacion_id = ?
    """, (id,)).fetchall()
    conn.close()

    # Convertir Row de sqlite3 a dict
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
        'piezas': [{'nombre': p['nombre'], 'cantidad': p['cantidad'],
                    'precio_venta': p['precio_venta']} for p in piezas],
    }

    # Generar PDF con tipo de documento
    pdf_buffer = generar_presupuesto_pdf(reparacion_data, tipo_documento=tipo_documento)
    
    # Retornar como descarga
    nombre_archivo = f"{tipo_documento}_reparacion_{id}.pdf"
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=nombre_archivo
    )

# =========================================
# 🔸 ADMINISTRACIÓN DE USUARIOS
# =========================================

# LISTAR USUARIOS
@app.route("/admin/usuarios")
@login_required
@role_required('admin')
def admin_usuarios():
    conn = get_db()
    usuarios = conn.execute("""
        SELECT id, usuario, rol, 
               (SELECT COUNT(*) FROM reparaciones_historial 
                WHERE usuario = usuarios.usuario) AS intervenciones
        FROM usuarios
        ORDER BY usuario ASC
    """).fetchall()
    conn.close()
    
    try:
        logger.info(json.dumps({
            "event": "admin_usuarios_viewed",
            "admin": session.get('usuario'),
            "total_usuarios": len(usuarios)
        }, ensure_ascii=False))
    except Exception:
        logger.info(f"admin_usuarios_viewed by {session.get('usuario')}")
    
    return render_template("admin_usuarios.html", usuarios=usuarios)


# CREAR USUARIO
@app.route("/admin/usuarios/nuevo", methods=["GET", "POST"])
@login_required
@role_required('admin')
@csrf_protect
def nuevo_usuario():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        contraseña = request.form.get("contraseña", "").strip()
        rol = request.form.get("rol", "tecnico").strip()
        
        # Validaciones
        if not usuario or len(usuario) < 3:
            flash("❌ Usuario debe tener al menos 3 caracteres.", "danger")
            return render_template("nuevo_usuario.html")
        
        if not contraseña:
            flash("❌ La contraseña es obligatoria.", "danger")
            return render_template("nuevo_usuario.html")

        pwd_ok, pwd_msg = validar_contraseña(contraseña)
        if not pwd_ok:
            flash(f"❌ {pwd_msg}", "danger")
            return render_template("nuevo_usuario.html")
        
        if rol not in ['admin', 'tecnico']:
            flash("❌ Rol inválido.", "danger")
            return render_template("nuevo_usuario.html")
        
        try:
            conn = get_db()
            hashed_pwd = generate_password_hash(contraseña)
            conn.execute("""
                INSERT INTO usuarios (usuario, contraseña, rol)
                VALUES (?, ?, ?)
            """, (usuario, hashed_pwd, rol))
            conn.commit()
            
            # Registrar auditoría
            registrar_auditoria(conn, 'usuario_created', session.get('usuario'), {
                'nuevo_usuario': usuario,
                'rol': rol
            }, ip_address=request.remote_addr)
            
            conn.close()
            
            try:
                logger.info(json.dumps({
                    "event": "usuario_created",
                    "admin": session.get('usuario'),
                    "nuevo_usuario": usuario,
                    "rol": rol
                }, ensure_ascii=False))
            except Exception:
                logger.info(f"usuario_created {usuario} rol={rol}")
            
            flash(f"✅ Usuario '{usuario}' creado correctamente.", "success")
            return redirect(url_for("admin_usuarios"))
        
        except Exception as e:
            conn.close() if conn else None
            error_msg = "El usuario ya existe" if "UNIQUE" in str(e) else str(e)
            flash(f"❌ Error: {error_msg}", "danger")
            return render_template("nuevo_usuario.html")
    
    return render_template("nuevo_usuario.html")


# EDITAR USUARIO
@app.route("/admin/usuarios/editar/<int:id>", methods=["GET", "POST"])
@login_required
@role_required('admin')
@csrf_protect
def editar_usuario(id):
    conn = get_db()
    usuario = conn.execute("SELECT * FROM usuarios WHERE id = ?", (id,)).fetchone()
    
    if not usuario:
        conn.close()
        flash("❌ Usuario no encontrado.", "danger")
        return redirect(url_for("admin_usuarios"))
    
    if request.method == "POST":
        rol = request.form.get("rol", "tecnico").strip()
        nueva_contraseña = request.form.get("nueva_contraseña", "").strip()
        
        if rol not in ['admin', 'tecnico']:
            flash("❌ Rol inválido.", "danger")
            conn.close()
            return render_template("editar_usuario.html", usuario=usuario)
        
        try:
            if nueva_contraseña:
                pwd_ok, pwd_msg = validar_contraseña(nueva_contraseña)
                if not pwd_ok:
                    flash(f"❌ {pwd_msg}", "danger")
                    conn.close()
                    return render_template("editar_usuario.html", usuario=usuario)
                
                hashed_pwd = generate_password_hash(nueva_contraseña)
                conn.execute("""
                    UPDATE usuarios
                    SET rol = ?, contraseña = ?
                    WHERE id = ?
                """, (rol, hashed_pwd, id))
            else:
                conn.execute("""
                    UPDATE usuarios
                    SET rol = ?
                    WHERE id = ?
                """, (rol, id))
            
            conn.commit()
            
            # Registrar auditoría
            registrar_auditoria(conn, 'usuario_updated', session.get('usuario'), {
                'usuario_id': id,
                'usuario_nombre': usuario['usuario'],
                'nuevo_rol': rol,
                'password_changed': bool(nueva_contraseña)
            }, ip_address=request.remote_addr)
            
            try:
                logger.info(json.dumps({
                    "event": "usuario_updated",
                    "admin": session.get('usuario'),
                    "usuario_id": id,
                    "usuario_nombre": usuario['usuario'],
                    "nuevo_rol": rol,
                    "password_changed": bool(nueva_contraseña)
                }, ensure_ascii=False))
            except Exception:
                logger.info(f"usuario_updated id={id} rol={rol}")
            
            flash(f"✅ Usuario '{usuario['usuario']}' actualizado correctamente.", "success")
            conn.close()
            return redirect(url_for("admin_usuarios"))
        
        except Exception as e:
            conn.close()
            flash(f"❌ Error al actualizar: {str(e)}", "danger")
            return render_template("editar_usuario.html", usuario=usuario)
    
    conn.close()
    return render_template("editar_usuario.html", usuario=usuario)


# BORRAR USUARIO
@app.route("/admin/usuarios/borrar/<int:id>")
@login_required
@role_required('admin')
def borrar_usuario(id):
    # Validar que no sea el mismo usuario logueado
    if session.get('usuario'):
        conn = get_db()
        usuario = conn.execute("SELECT usuario FROM usuarios WHERE id = ?", (id,)).fetchone()
        
        if usuario and usuario['usuario'] == session.get('usuario'):
            conn.close()
            flash("❌ No puedes borrar tu propia cuenta.", "danger")
            return redirect(url_for("admin_usuarios"))
        
        try:
            usuario_nombre = usuario['usuario'] if usuario else f"ID {id}"
            conn.execute("DELETE FROM usuarios WHERE id = ?", (id,))
            conn.commit()
            
            # Registrar auditoría
            registrar_auditoria(conn, 'usuario_deleted', session.get('usuario'), {
                'usuario_id': id,
                'usuario_nombre': usuario_nombre
            }, ip_address=request.remote_addr)
            
            try:
                logger.info(json.dumps({
                    "event": "usuario_deleted",
                    "admin": session.get('usuario'),
                    "usuario_id": id,
                    "usuario_nombre": usuario_nombre
                }, ensure_ascii=False))
            except Exception:
                logger.info(f"usuario_deleted id={id}")
            
            flash(f"✅ Usuario '{usuario_nombre}' eliminado correctamente.", "success")
        
        except Exception as e:
            flash(f"❌ Error al eliminar: {str(e)}", "danger")
        
        finally:
            conn.close()
    
    return redirect(url_for("admin_usuarios"))

# =========================================
# 🔸 SECCIÓN CONTACTO
# =========================================

@app.route("/contacto", methods=["GET", "POST"])
@csrf_protect
def contacto():
    if request.method == "POST":
        nombre = request.form["nombre"]
        email = request.form["email"]
        telefono = request.form["telefono"]
        tipo = request.form["tipo"]
        mensaje = request.form["mensaje"]

        # Aquí simplemente imprimimos los datos en consola
        # (luego lo cambiamos por enviar email real si quieres)
        try:
            logger.info(json.dumps({
                "event": "contacto_enviado",
                "nombre": nombre,
                "email": email,
                "telefono": telefono,
                "tipo": tipo
            }, ensure_ascii=False))
        except Exception:
            logger.info(f"contacto_enviado nombre={nombre} email={email} tipo={tipo}")

        return render_template("contacto_exito.html", nombre=nombre)

    return render_template("contacto.html")

# =========================================
# 🔸 SECCIÓN SOBRE NOSOTROS
# =========================================

@app.route("/sobre")
def sobre():
    return render_template("sobre_nosotros.html")

# =========================================
# 🔸 SECCIÓN SERVICIOS
# =========================================

@app.route("/servicios")
def servicios():
    return render_template("servicios.html")

# =========================================
# 🔸 CONSULTA PÚBLICA DE REPARACIONES
# =========================================

@app.route("/consulta", methods=["GET", "POST"])
@csrf_protect
def consulta():
    reparacion = None
    error = None

    if request.method == "POST":
        id_reparacion = request.form.get("id_reparacion")

        if not id_reparacion:
            error = "Por favor, introduce un número de reparación."
        else:
            try:
                id_reparacion = int(id_reparacion)
                conn = get_db()
                reparacion = conn.execute("""
                    SELECT reparaciones.id, reparaciones.dispositivo, reparaciones.estado,
                           reparaciones.fecha_entrada, reparaciones.precio, reparaciones.descripcion,
                           clientes.nombre as cliente, clientes.telefono, clientes.email as cliente_email,
                           reparaciones.estado_pago, reparaciones.fecha_pago, reparaciones.metodo_pago
                    FROM reparaciones
                    JOIN clientes ON clientes.id = reparaciones.cliente_id
                    WHERE reparaciones.id = ?
                """, (id_reparacion,)).fetchone()
                conn.close()

                if not reparacion:
                    error = f"No se encontró ninguna reparación con el número {id_reparacion}."

            except ValueError:
                error = "Por favor, introduce un número válido."

    return render_template("consulta.html", reparacion=reparacion, error=error)


@app.route("/mis-reparaciones", methods=["GET", "POST"])
@csrf_protect
def mis_reparaciones():
    """Panel publico: el cliente introduce su email y ve todas sus reparaciones."""
    reparaciones_list = None
    cliente_nombre = None
    email_buscado = None
    error = None

    if request.method == "POST":
        email_buscado = request.form.get("email", "").strip().lower()
        if not email_buscado or '@' not in email_buscado:
            error = "Por favor, introduce un email valido."
        else:
            conn = get_db()
            cliente = conn.execute(
                "SELECT id, nombre FROM clientes WHERE LOWER(email) = ?",
                (email_buscado,)
            ).fetchone()

            if not cliente:
                error = "No se encontro ningun cliente con ese email."
                conn.close()
            else:
                cliente_nombre = cliente['nombre']
                reparaciones_list = conn.execute('''
                    SELECT r.id, r.dispositivo, r.descripcion, r.estado,
                           r.estado_pago, r.precio, r.fecha_entrada,
                           r.fecha_pago, r.metodo_pago
                    FROM reparaciones r
                    WHERE r.cliente_id = ?
                    ORDER BY r.fecha_entrada DESC
                ''', (cliente['id'],)).fetchall()
                conn.close()

                if not reparaciones_list:
                    error = "No se encontraron reparaciones asociadas a este email."
                    reparaciones_list = None

    return render_template("mis_reparaciones.html",
        reparaciones=reparaciones_list,
        cliente_nombre=cliente_nombre,
        email_buscado=email_buscado,
        error=error
    )


@app.route('/publico/pagar/<int:id>', methods=['POST'])
@csrf_protect
def publico_pagar(id):
    """Endpoint de pago público. Verificación por email antes de crear sesión Stripe."""
    # 1. Validar email
    cliente_email = request.form.get('cliente_email', '').strip().lower()
    if not cliente_email or '@' not in cliente_email:
        flash('⚠️ Debes proporcionar un correo válido (ej: cliente@ejemplo.com).', 'danger')
        return redirect(url_for('consulta'))

    conn = get_db()
    try:
        reparacion = conn.execute(
            """SELECT r.id, r.precio, r.estado_pago, c.email as cliente_email, c.nombre as cliente_nombre
               FROM reparaciones r
               JOIN clientes c ON c.id = r.cliente_id
               WHERE r.id = ?""", (id,)
        ).fetchone()
    except Exception as e:
        conn.close()
        flash(f'❌ Error al buscar la reparación: {str(e)}', 'danger')
        return redirect(url_for('consulta'))

    # 2. Validar que reparación existe
    if not reparacion:
        conn.close()
        flash(f'❌ Reparación #{id} no encontrada en el sistema.', 'danger')
        return redirect(url_for('consulta'))

    # 3. Validar que NO está ya pagada
    if reparacion['estado_pago'] == 'Pagado':
        conn.close()
        flash('✅ Esta reparación ya está pagada. No se puede procesar otro pago.', 'info')
        return redirect(url_for('consulta'))

    # 4. Validar precio existe y es > 0
    try:
        precio = float(reparacion['precio']) if reparacion['precio'] else 0
        if precio <= 0:
            conn.close()
            flash('❌ No hay un importe válido a pagar para esta reparación.', 'danger')
            return redirect(url_for('consulta'))
    except (ValueError, TypeError):
        conn.close()
        flash('❌ Error: el precio no es válido.', 'danger')
        return redirect(url_for('consulta'))

    # 5. Validar email coincide con cliente registrado
    cliente_email_bd = str(reparacion['cliente_email'] or '').strip().lower()
    if not cliente_email_bd:
        conn.close()
        flash('❌ El cliente no tiene email registrado. Contacta con administración.', 'danger')
        return redirect(url_for('consulta'))

    if cliente_email != cliente_email_bd:
        conn.close()
        flash('❌ El correo no coincide con el cliente registrado para esta reparación.', 'danger')
        return redirect(url_for('consulta'))

    # 6. Validar Stripe configurado
    if not STRIPE_SECRET_KEY or stripe is None:
        conn.close()
        flash('⚠️ El sistema de pagos no está configurado. Contacta con el administrador.', 'danger')
        return redirect(url_for('consulta'))
    # si la clave se ve como pública, advertir al usuario/administrador
    if STRIPE_SECRET_KEY.startswith('pk_'):
        conn.close()
        logger.warning('Stripe secret key parece una clave pública (pk_...).')
        flash('❌ Clave secreta de Stripe inválida. Verifica las variables de entorno.', 'danger')
        return redirect(url_for('consulta'))

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
            cancel_url=url_for('consulta', _external=True),
            metadata={
                'reparacion_id': str(id),
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
        conn.close()
        return redirect(checkout_session.url, code=303)
    except stripe.error.CardError as e:
        conn.close()
        flash(f'❌ Error de tarjeta: {e.user_message}', 'danger')
        return redirect(url_for('consulta'))
    except stripe.error.RateLimitError:
        conn.close()
        flash('❌ Demasiadas solicitudes. Intenta de nuevo en unos momentos.', 'danger')
        return redirect(url_for('consulta'))
    except stripe.error.InvalidRequestError as e:
        conn.close()
        flash(f'❌ Error en la solicitud: {e.user_message}', 'danger')
        return redirect(url_for('consulta'))
    except stripe.error.AuthenticationError as e:
        # log masked key and error message for admin debugging
        logger.error(
            "Stripe authentication failed when creating checkout session. "
            "api_key=%s message=%s",
            _mask_key(stripe.api_key) if stripe and getattr(stripe, 'api_key', None) else None,
            str(e.user_message or e)
        )
        conn.close()
        flash('❌ Error de autenticación con Stripe. Verifica las claves.', 'danger')
        return redirect(url_for('consulta'))
    except stripe.error.APIConnectionError:
        conn.close()
        flash('❌ Error de conexión con Stripe. Intenta de nuevo más tarde.', 'danger')
        return redirect(url_for('consulta'))
    except Exception as e:
        conn.close()
        flash(f'❌ Error inesperado al crear la sesión de pago: {str(e)}', 'danger')
        logger.exception(json.dumps({
            "event": "publico_pagar_error",
            "error": str(e)
        }, ensure_ascii=False))
        return redirect(url_for('consulta'))


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

    # 2. Construir y validar evento
    try:
        # Si la librería stripe está disponible, usar la verificación de firma
        if stripe and hasattr(stripe, 'Webhook'):
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
            logger.info(f'[WEBHOOK] ✅ Evento válido: {event.get("type")}')
        else:
            # En entornos de test/local sin stripe instalado, permitir payload JSON directamente
            event = json.loads(payload.decode('utf-8') if isinstance(payload, (bytes, bytearray)) else payload)
            logger.info(f'[WEBHOOK] ⚠️ stripe no disponible, usando payload directo para evento: {event.get("type")}')
    except Exception as e:
        # Manejar tanto SignatureVerificationError (si stripe está presente) como errores de parsing
        logger.error(f'[WEBHOOK] ❌ Error al procesar evento: {str(e)}')
        return jsonify({'error': str(e)}), 400

    # 3. Procesar evento checkout.session.completed
    if event['type'] == 'checkout.session.completed':
        session_obj = event['data']['object']
        metadata = session_obj.get('metadata', {})
        reparacion_id = metadata.get('reparacion_id')
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

        # Actualizar BD con validaciones adicionales
        conn = None
        try:
            conn = get_db()

            # Verificar que reparación existe
            reparacion = conn.execute(
                'SELECT id, estado_pago, precio FROM reparaciones WHERE id = ?',
                (reparacion_id,)
            ).fetchone()

            if not reparacion:
                logger.error(json.dumps({
                    "event": "webhook_missing_reparacion",
                    "reparacion_id": reparacion_id,
                    "session_id": session_id
                }, ensure_ascii=False))
                return jsonify({'error': f'Repair #{reparacion_id} not found'}), 404

            # Verificar que NO está ya pagada
            if reparacion['estado_pago'] == 'Pagado':
                logger.warning(json.dumps({
                    "event": "webhook_already_paid",
                    "reparacion_id": reparacion_id,
                    "session_id": session_id
                }, ensure_ascii=False))
                return jsonify({'status': 'already_paid'}), 200

            # Si Stripe reporta importe, compararlo con precio de la reparación
            if amount_total is not None and reparacion['precio'] is not None:
                # convertir a unidades (centavos -> moneda)
                reported = float(amount_total) / 100.0
                expected = float(reparacion['precio'])
                # tolerancia pequeña para decimales
                if abs(reported - expected) > 0.01:
                    logger.warning(json.dumps({
                        "event": "webhook_amount_mismatch",
                        "reparacion_id": reparacion_id,
                        "session_id": session_id,
                        "reported_amount": reported,
                        "expected_amount": expected
                    }, ensure_ascii=False))
                    # Registrar auditoría del desacuerdo pero proceder a marcar como pagada

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
            fecha_pago = datetime.now().strftime('%Y-%m-%d')
            metodo_pago = 'Tarjeta (Stripe)'

            conn.execute(
                'UPDATE reparaciones SET estado_pago=?, fecha_pago=?, metodo_pago=? WHERE id=?',
                ('Pagado', fecha_pago, metodo_pago, reparacion_id)
            )
            conn.commit()

            # Registrar auditoría y log estructurado
            try:
                registrar_auditoria(conn, 'pago_registrado', None, {
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
                reparacion_data = conn.execute('''
                    SELECT r.*, c.nombre, c.email, c.telefono
                    FROM reparaciones r
                    JOIN clientes c ON r.cliente_id = c.id
                    WHERE r.id = ?
                ''', (reparacion_id,)).fetchone()

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
                        }
                        pdf_buffer = generar_presupuesto_pdf(pdf_reparacion, tipo_documento="factura")
                    except Exception:
                        logger.exception(f'[WEBHOOK] Error generando PDF para reparacion {reparacion_id}, se enviara email sin adjunto')

                    # Enviar email de confirmación con factura PDF adjunta
                    email_service.send_payment_confirmation(
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
            if conn:
                conn.close()

    else:
        logger.info(f'[WEBHOOK] ℹ️ Evento no procesado: {event["type"]}')

    return jsonify({'status': 'received'}), 200


# Health endpoint
@app.route('/health')
def health():
    return jsonify(status='OK'), 200


# Global error handlers
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
#     conn = get_db()
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
if __name__ == "__main__":
    app.run(debug=True)
