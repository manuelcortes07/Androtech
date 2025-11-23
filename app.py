from flask import Flask, render_template, request, redirect
import sqlite3

app = Flask(__name__)

def get_db():
    conn = sqlite3.connect("database/andro_tech.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)

#LISTAR CLIENTES

@app.route("/clientes")
def clientes():
    conn = get_db()
    clientes = conn.execute("SELECT * FROM clientes").fetchall()
    conn.close()
    return render_template("clientes.html", clientes=clientes)

#CREAR CLIENTE

@app.route("/clientes/nuevo", methods=["GET", "POST"])
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

        return redirect("/clientes")

    return render_template("nuevo_cliente.html")

#EDITAR CLIENTE

@app.route("/clientes/editar/<int:id>", methods=["GET", "POST"])
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

        return redirect("/clientes")

    cliente = conn.execute("SELECT * FROM clientes WHERE id=?", (id,)).fetchone()
    conn.close()

    return render_template("editar_cliente.html", cliente=cliente)

#BORRAR CLIENTE

@app.route("/clientes/borrar/<int:id>")
def borrar_cliente(id):
    conn = get_db()
    conn.execute("DELETE FROM clientes WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/clientes")

#LISTA DE REPARACIONES

@app.route("/reparaciones")
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

#NUEVA REPARACION

@app.route("/reparaciones/nueva", methods=["GET", "POST"])
def nueva_reparacion():
    conn = get_db()

    if request.method == "POST":
        cliente_id = request.form["cliente_id"]
        dispositivo = request.form["dispositivo"]
        descripcion = request.form["descripcion"]
        estado = request.form["estado"]
        precio = request.form["precio"]

        conn.execute("""
            INSERT INTO reparaciones (cliente_id, dispositivo, descripcion, estado, fecha_entrada, precio)
            VALUES (?, ?, ?, ?, DATE('now'), ?)
        """, (cliente_id, dispositivo, descripcion, estado, precio))
        
        conn.commit()
        conn.close()
        return redirect("/reparaciones")

    clientes = conn.execute("SELECT * FROM clientes").fetchall()
    conn.close()

    return render_template("nueva_reparacion.html", clientes=clientes)

#EDITAR REPARACION

@app.route("/reparaciones/editar/<int:id>", methods=["GET", "POST"])
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
        return redirect("/reparaciones")

    reparacion = conn.execute("SELECT * FROM reparaciones WHERE id=?", (id,)).fetchone()
    clientes = conn.execute("SELECT * FROM clientes").fetchall()
    conn.close()

    return render_template("editar_reparacion.html", reparacion=reparacion, clientes=clientes)

#BORRAR REPARACION

@app.route("/reparaciones/borrar/<int:id>")
def borrar_reparacion(id):
    conn = get_db()
    conn.execute("DELETE FROM reparaciones WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/reparaciones")

