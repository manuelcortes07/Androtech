from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_muy_segura_aqui'  # Cambia esto por una clave segura en producción

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

    # Estadísticas principales
    total_clientes = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    reparaciones_activas = conn.execute("""
        SELECT COUNT(*) FROM reparaciones
        WHERE estado != 'Terminado' AND estado != 'Entregado'
    """).fetchone()[0]
    reparaciones_terminadas = conn.execute("""
        SELECT COUNT(*) FROM reparaciones
        WHERE estado = 'Terminado' OR estado = 'Entregado'
    """).fetchone()[0]
    ingresos = conn.execute("""
        SELECT IFNULL(SUM(precio), 0) FROM reparaciones
    """).fetchone()[0]

    # Calcular porcentajes para las barras de progreso
    total_reparaciones = reparaciones_activas + reparaciones_terminadas
    porcentaje_activas = round((reparaciones_activas / total_reparaciones * 100), 1) if total_reparaciones > 0 else 0
    porcentaje_terminadas = round((reparaciones_terminadas / total_reparaciones * 100), 1) if total_reparaciones > 0 else 0

    # Últimas 5 reparaciones con información del cliente
    ultimas_reparaciones = conn.execute("""
        SELECT reparaciones.*, clientes.nombre AS cliente
        FROM reparaciones
        LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id
        ORDER BY reparaciones.id DESC
        LIMIT 5
    """).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        total_clientes=total_clientes,
        reparaciones_activas=reparaciones_activas,
        reparaciones_terminadas=reparaciones_terminadas,
        ingresos=ingresos,
        porcentaje_activas=porcentaje_activas,
        porcentaje_terminadas=porcentaje_terminadas,
        ultimas_reparaciones=ultimas_reparaciones
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
    conn = get_db()
    sql = """
    SELECT reparaciones.*, clientes.nombre AS cliente
    FROM reparaciones
    LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id
    """
    datos = conn.execute(sql).fetchall()
    conn.close()
    return render_template("reparaciones.html", reparaciones=datos)


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
    conn.execute("DELETE FROM reparaciones WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("reparaciones"))

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
    reparaciones = []
    error = None

    if request.method == "POST":
        telefono = request.form.get("telefono")

        if not telefono:
            error = "Por favor, introduce un número de teléfono."
        else:
            conn = get_db()
            reparaciones = conn.execute("""
                SELECT reparaciones.id, reparaciones.dispositivo, reparaciones.estado,
                       reparaciones.fecha_entrada, reparaciones.precio
                FROM reparaciones
                JOIN clientes ON clientes.id = reparaciones.cliente_id
                WHERE clientes.telefono = ?
                ORDER BY reparaciones.fecha_entrada DESC
            """, (telefono,)).fetchall()
            conn.close()

            if not reparaciones:
                error = f"No se encontraron reparaciones para el teléfono {telefono}."

    return render_template("consulta.html", reparaciones=reparaciones, error=error)

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
