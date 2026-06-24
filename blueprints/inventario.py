"""Blueprint de inventario / piezas (refactor B1).

Inventario de piezas (CRUD + API de búsqueda) y el uso de piezas en una
reparación (alta/baja con ajuste de stock). Comportamiento idéntico al que tenían
en app.py; sólo cambia el nombre de endpoint (inventario → inventario.inventario,
etc.). Las redirecciones al detalle de una reparación apuntan a
`reparaciones.editar_reparacion` (ya migrado a su propio blueprint).
"""

from __future__ import annotations

from datetime import datetime

from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func, select

from auth import login_required, permiso_requerido
from database import get_session
from models import InventarioPieza, PiezaReparacion
from utils.security import csrf_protect

bp = Blueprint("inventario", __name__)


@bp.route("/inventario")
@login_required
@permiso_requerido('inventario_ver')
def inventario():
    # Fase 1.6: listado con filtros vía ORM
    buscar = request.args.get('q', '').strip()
    categoria = request.args.get('categoria', '').strip()

    # ⚠️ select(Model.__table__) es Core → el filtro automático NO se aplica.
    # Filtro de taller MANUAL como primera cláusula (Fase 2.5).
    stmt = select(InventarioPieza.__table__).where(
        InventarioPieza.__table__.c.taller_id == g.taller_id
    )
    if buscar:
        like = f"%{buscar}%"
        stmt = stmt.where(
            InventarioPieza.__table__.c.nombre.like(like)
            | InventarioPieza.__table__.c.proveedor.like(like)
        )
    if categoria:
        stmt = stmt.where(InventarioPieza.__table__.c.categoria == categoria)
    stmt = stmt.order_by(InventarioPieza.__table__.c.nombre.asc())

    with get_session() as s:
        piezas = s.execute(stmt).mappings().all()

    # KPIs
    total = len(piezas)
    stock_bajo = sum(1 for p in piezas if p['cantidad'] <= p['cantidad_minima'])
    valor_total = sum((p['precio_coste'] or 0) * (p['cantidad'] or 0) for p in piezas)

    return render_template("inventario.html", piezas=piezas, total=total,
                           stock_bajo=stock_bajo, valor_total=valor_total,
                           buscar=buscar, categoria=categoria)


@bp.route("/inventario/nueva", methods=["GET", "POST"])
@login_required
@permiso_requerido('inventario_crear')
@csrf_protect
def nueva_pieza():
    if request.method == "POST":
        with get_session() as s:
            s.add(InventarioPieza(
                nombre=request.form['nombre'],
                categoria=request.form.get('categoria', 'General'),
                descripcion=request.form.get('descripcion', ''),
                cantidad=int(request.form.get('cantidad', 0)),
                cantidad_minima=int(request.form.get('cantidad_minima', 5)),
                precio_coste=float(request.form.get('precio_coste', 0) or 0),
                precio_venta=float(request.form.get('precio_venta', 0) or 0),
                proveedor=request.form.get('proveedor', ''),
                ubicacion=request.form.get('ubicacion', ''),
                fecha_actualizacion=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            ))
            s.commit()
        flash('Pieza añadida al inventario.', 'success')
        return redirect(url_for('inventario.inventario'))
    return render_template("nueva_pieza.html")


@bp.route("/inventario/editar/<int:id>", methods=["GET", "POST"])
@login_required
@permiso_requerido('inventario_editar')
@csrf_protect
def editar_pieza(id):
    if request.method == "POST":
        with get_session() as s:
            pieza = s.get(InventarioPieza, id)
            if pieza:
                pieza.nombre = request.form['nombre']
                pieza.categoria = request.form.get('categoria', 'General')
                pieza.descripcion = request.form.get('descripcion', '')
                pieza.cantidad = int(request.form.get('cantidad', 0))
                pieza.cantidad_minima = int(request.form.get('cantidad_minima', 5))
                pieza.precio_coste = float(request.form.get('precio_coste', 0) or 0)
                pieza.precio_venta = float(request.form.get('precio_venta', 0) or 0)
                pieza.proveedor = request.form.get('proveedor', '')
                pieza.ubicacion = request.form.get('ubicacion', '')
                pieza.fecha_actualizacion = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                s.commit()
        flash('Pieza actualizada.', 'success')
        return redirect(url_for('inventario.inventario'))

    with get_session() as s:
        pieza = s.get(InventarioPieza, id)
    if not pieza:
        flash('Pieza no encontrada.', 'danger')
        return redirect(url_for('inventario.inventario'))
    return render_template("editar_pieza.html", pieza=pieza)


@bp.route("/inventario/eliminar/<int:id>")
@login_required
@permiso_requerido('inventario_borrar')
def eliminar_pieza(id):
    with get_session() as s:
        en_uso = s.scalar(
            select(func.count()).select_from(PiezaReparacion)
            .where(PiezaReparacion.pieza_id == id)
        )
        if en_uso > 0:
            flash(f'No se puede eliminar: esta pieza está asociada a {en_uso} reparación(es).', 'danger')
            return redirect(url_for('inventario.inventario'))
        pieza = s.get(InventarioPieza, id)
        if pieza:
            s.delete(pieza)
            s.commit()
    flash('Pieza eliminada del inventario.', 'success')
    return redirect(url_for('inventario.inventario'))


@bp.route("/api/inventario/buscar")
@login_required
def api_buscar_piezas():
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])
    with get_session() as s:
        rows = s.execute(
            select(
                InventarioPieza.id, InventarioPieza.nombre,
                InventarioPieza.cantidad, InventarioPieza.precio_venta,
            ).where(InventarioPieza.nombre.like(f"%{q}%")).limit(10)
        ).mappings().all()
    return jsonify([dict(r) for r in rows])


@bp.route("/reparaciones/<int:id>/piezas", methods=["POST"])
@login_required
@csrf_protect
def agregar_pieza_reparacion(id):
    pieza_id = int(request.form['pieza_id'])
    cantidad = int(request.form.get('cantidad', 1))

    with get_session() as s:
        pieza = s.get(InventarioPieza, pieza_id)
        if not pieza:
            flash('Pieza no encontrada.', 'danger')
            return redirect(url_for('reparaciones.editar_reparacion', id=id))

        if pieza.cantidad < cantidad:
            flash(f'Stock insuficiente. Disponible: {pieza.cantidad}', 'warning')
            return redirect(url_for('reparaciones.editar_reparacion', id=id))

        s.add(PiezaReparacion(
            reparacion_id=id, pieza_id=pieza_id, cantidad=cantidad,
            fecha_uso=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            usuario=session.get('usuario'),
        ))
        pieza.cantidad = pieza.cantidad - cantidad
        pieza.fecha_actualizacion = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        pieza_nombre = pieza.nombre
        s.commit()
    flash(f'Pieza "{pieza_nombre}" x{cantidad} añadida a la reparación.', 'success')
    return redirect(url_for('reparaciones.editar_reparacion', id=id))


@bp.route("/reparaciones/piezas/<int:uso_id>/eliminar", methods=["POST"])
@login_required
@csrf_protect
def eliminar_pieza_reparacion(uso_id):
    with get_session() as s:
        uso = s.get(PiezaReparacion, uso_id)
        if not uso:
            flash('Registro no encontrado.', 'danger')
            return redirect(url_for('reparaciones.reparaciones'))

        reparacion_id = uso.reparacion_id
        # Restaurar stock
        pieza = s.get(InventarioPieza, uso.pieza_id)
        if pieza:
            pieza.cantidad = pieza.cantidad + uso.cantidad
            pieza.fecha_actualizacion = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        s.delete(uso)
        s.commit()
    flash('Pieza devuelta al inventario.', 'success')
    return redirect(url_for('reparaciones.editar_reparacion', id=reparacion_id))
