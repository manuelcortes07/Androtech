from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
import sqlite3
import os
from datetime import datetime
try:
    import stripe
except ImportError:
    stripe = None
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from utils.pdf_generator import generar_presupuesto_pdf

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_muy_segura_aqui'  # Cambia esto por una clave segura en producción

# Stripe configuration (use environment variables in production)
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

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

# CONEXIÓN A LA BASE DE DATOS
def get_db():
    conn = sqlite3.connect("database/andro_tech.db")
    conn.row_factory = sqlite3.Row
    return conn

# DECORADOR PARA REQUERIR LOGIN
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            flash('Debes iniciar sesión para acceder a esta página.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# DECORADOR PARA REQUERIR ROL ESPECÍFICO (OPCIONAL)
def role_required(rol_requerido):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if session.get('rol') != rol_requerido:
                flash('No tienes permisos para acceder a esta página.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# =========================================
# 🔸 AUTENTICACIÓN
# =========================================

# LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        contraseña = request.form["contraseña"]

        conn = get_db()
        user = conn.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
        conn.close()

        if user and check_password_hash(user["contraseña"], contraseña):
            session["usuario"] = user["usuario"]
            session["rol"] = user["rol"]
            flash(f"Bienvenido, {user['usuario']}!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Usuario o contraseña incorrectos.", "danger")

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
    conn.close()
    return render_template("index.html", total_clientes=total_clientes, activas=activas, terminadas=terminadas, ingresos=ingresos)

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
    
    conn.close()
    
    # Calcular IVA en ingresos
    iva_total = round(ingresos_total * 0.21, 2)
    iva_mes = round(ingresos_mes * 0.21, 2)

    return render_template(
        "dashboard.html",
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
        reparaciones_sin_pagar=reparaciones_sin_pagar_list
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

        return redirect(url_for("clientes"))

    return render_template("nuevo_cliente.html")


# EDITAR CLIENTE
@app.route("/clientes/editar/<int:id>", methods=["GET", "POST"])
@login_required
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
#  🔸 SECCIÓN REPARACIONES
# =========================================

# LISTAR REPARACIONES
@app.route("/reparaciones")
@login_required
def reparaciones():
    import urllib.parse

    conn = get_db()

    # Recoger filtros desde query string
    cliente_id = request.args.get('cliente_id', '').strip()
    estado = request.args.get('estado', '').strip()
    desde = request.args.get('desde', '').strip()
    hasta = request.args.get('hasta', '').strip()
    precio_min = request.args.get('precio_min', '').strip()
    precio_max = request.args.get('precio_max', '').strip()

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

    filters_query = urllib.parse.urlencode(filters)

    total_pages = max(1, (total + per_page - 1) // per_page)

    return render_template("reparaciones.html", reparaciones=datos, clientes=clientes, filters=filters, filters_query=filters_query, page=page, total_pages=total_pages, per_page=per_page, total=total)


# NUEVA REPARACIÓN
@app.route("/reparaciones/nueva", methods=["GET", "POST"])
@login_required
def nueva_reparacion():
    conn = get_db()

    if request.method == "POST":
        cliente_id = request.form["cliente_id"]
        dispositivo = request.form["dispositivo"]
        descripcion = request.form["descripcion"]
        estado = request.form["estado"]
        precio = request.form["precio"]

        fecha_entrada = datetime.now().strftime("%Y-%m-%d")

        conn.execute("""
            INSERT INTO reparaciones (cliente_id, dispositivo, descripcion, estado, fecha_entrada, precio)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (cliente_id, dispositivo, descripcion, estado, fecha_entrada, precio))
        
        conn.commit()
        conn.close()
        return redirect(url_for("reparaciones"))

    clientes = conn.execute("SELECT * FROM clientes").fetchall()
    conn.close()

    return render_template("nueva_reparacion.html", clientes=clientes)


# EDITAR REPARACIÓN
@app.route("/reparaciones/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_reparacion(id):
    conn = get_db()

    if request.method == "POST":
        cliente_id = request.form["cliente_id"]
        dispositivo = request.form["dispositivo"]
        descripcion = request.form["descripcion"]
        estado = request.form["estado"]
        precio = request.form["precio"]

        conn.execute("""
            UPDATE reparaciones
            SET cliente_id=?, dispositivo=?, descripcion=?, estado=?, precio=?
            WHERE id=?
        """, (cliente_id, dispositivo, descripcion, estado, precio, id))

        conn.commit()
        conn.close()
        return redirect(url_for("reparaciones"))

    reparacion = conn.execute("SELECT * FROM reparaciones WHERE id=?", (id,)).fetchone()
    clientes = conn.execute("SELECT * FROM clientes").fetchall()
    conn.close()

    return render_template("editar_reparacion.html", reparacion=reparacion, clientes=clientes)


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
    
    conn.execute("DELETE FROM reparaciones WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('✅ Reparación eliminada correctamente.', 'success')
    return redirect(url_for("reparaciones"))


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
        SELECT r.*, c.nombre AS cliente_nombre, c.telefono AS cliente_telefono
        FROM reparaciones r
        LEFT JOIN clientes c ON c.id = r.cliente_id
        WHERE r.id = ?
    """, (id,)).fetchone()
    
    conn.close()
    
    if not reparacion:
        flash('Reparación no encontrada.', 'danger')
        return redirect(url_for('reparaciones'))
    
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
# 🔸 SECCIÓN CONTACTO
# =========================================

@app.route("/contacto", methods=["GET", "POST"])
def contacto():
    if request.method == "POST":
        nombre = request.form["nombre"]
        email = request.form["email"]
        telefono = request.form["telefono"]
        tipo = request.form["tipo"]
        mensaje = request.form["mensaje"]

        # Aquí simplemente imprimimos los datos en consola
        # (luego lo cambiamos por enviar email real si quieres)
        print("\n --- NUEVO MENSAJE DE CONTACTO ---")
        print("Nombre:", nombre)
        print("Email:", email)
        print("Teléfono:", telefono)
        print("Tipo:", tipo)
        print("Mensaje:", mensaje)
        print("----------------------------------\n")

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


@app.route('/publico/pagar/<int:id>', methods=['POST'])
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

    # 7. Crear sesión Stripe Checkout
    try:
        amount_cents = int(round(precio * 100))
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': f"Reparación #{id} - {reparacion['cliente_nombre'] or 'Cliente'}"
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
                'cliente_nombre': reparacion.get('cliente_nombre', '')
            }
        )
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
    except stripe.error.AuthenticationError:
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
        print(f'[ERROR] publico_pagar: {str(e)}')
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
        print('[WEBHOOK] ❌ Error: STRIPE_WEBHOOK_SECRET no configurado')
        return jsonify({'error': 'Webhook secret not configured'}), 400

    if not sig_header:
        print('[WEBHOOK] ❌ Error: Stripe-Signature header no encontrado')
        return jsonify({'error': 'Missing Stripe-Signature header'}), 400

    # 2. Construir y validar evento
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        print(f'[WEBHOOK] ✅ Evento válido: {event["type"]}')
    except stripe.error.SignatureVerificationError as e:
        print(f'[WEBHOOK] ❌ Error de firma: {str(e)}')
        return jsonify({'error': 'Invalid signature'}), 400
    except Exception as e:
        print(f'[WEBHOOK] ❌ Error al procesar evento: {str(e)}')
        return jsonify({'error': str(e)}), 400

    # 3. Procesar evento checkout.session.completed
    if event['type'] == 'checkout.session.completed':
        session_obj = event['data']['object']
        metadata = session_obj.get('metadata', {})
        reparacion_id = metadata.get('reparacion_id')
        cliente_email = metadata.get('cliente_email', 'unknown')

        # Validar metadata
        if not reparacion_id:
            print('[WEBHOOK] ❌ Error: reparacion_id no encontrado en metadata')
            return jsonify({'error': 'Missing reparacion_id in metadata'}), 400

        # Actualizar BD
        conn = None
        try:
            conn = get_db()

            # Verificar que reparación existe
            reparacion = conn.execute(
                'SELECT id, estado_pago, precio FROM reparaciones WHERE id = ?',
                (reparacion_id,)
            ).fetchone()

            if not reparacion:
                print(f'[WEBHOOK] ❌ Error: Reparación #{reparacion_id} no encontrada')
                return jsonify({'error': f'Repair #{reparacion_id} not found'}), 404

            # Verificar que NO está ya pagada
            if reparacion['estado_pago'] == 'Pagado':
                print(f'[WEBHOOK] ⚠️ Advertencia: Reparación #{reparacion_id} ya está pagada')
                return jsonify({'status': 'already_paid'}), 200

            # Marcar como pagada
            fecha_pago = datetime.now().strftime('%Y-%m-%d')
            metodo_pago = 'Tarjeta (Stripe)'

            conn.execute(
                'UPDATE reparaciones SET estado_pago=?, fecha_pago=?, metodo_pago=? WHERE id=?',
                ('Pagado', fecha_pago, metodo_pago, reparacion_id)
            )
            conn.commit()

            print(f'[WEBHOOK] ✅ Reparación #{reparacion_id} marcada como pagada (email: {cliente_email})')

        except Exception as e:
            print(f'[WEBHOOK] ❌ Error al actualizar BD: {str(e)}')
            return jsonify({'error': str(e)}), 500

        finally:
            if conn:
                conn.close()

    else:
        print(f'[WEBHOOK] ℹ️ Evento no procesado: {event["type"]}')

    return jsonify({'status': 'received'}), 200

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
