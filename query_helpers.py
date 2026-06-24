"""Helpers de consulta compartidos entre dominios (refactor B1).

`build_reparaciones_filters` (filtros del listado de reparaciones) y
`_ultimas_actualizaciones` (última fecha de cambio por reparación, sin N+1) los
usan varios blueprints (clientes, reparaciones, dashboard). Se extraen aquí para
importarlos sin ciclar con app.py. `app.py` los re-exporta (los tests referencian
`app._ultimas_actualizaciones`).
"""

from __future__ import annotations

from sqlalchemy import func, select

from models import RepairHistorial


def build_reparaciones_filters(args):
    """Construye cláusula WHERE y parámetros a partir de query params.

    args: objeto parecido a dict (p. ej. request.args)
    Devuelve (where_clause, params_dict)
    """
    # Fase 1.5b: binds con nombre (dict) para ejecutarse vía SQLAlchemy text().
    clauses = []
    params = {}

    cliente = args.get('cliente')
    if cliente:
        clauses.append("clientes.nombre LIKE :f_cliente")
        params['f_cliente'] = f"%{cliente}%"

    estado = args.get('estado')
    if estado:
        clauses.append("reparaciones.estado = :f_estado")
        params['f_estado'] = estado

    pago = args.get('pago')
    if pago:
        clauses.append("reparaciones.estado_pago = :f_pago")
        params['f_pago'] = pago

    fecha_desde = args.get('fecha_desde')
    if fecha_desde:
        clauses.append("reparaciones.fecha_entrada >= :f_desde")
        params['f_desde'] = fecha_desde

    fecha_hasta = args.get('fecha_hasta')
    if fecha_hasta:
        clauses.append("reparaciones.fecha_entrada <= :f_hasta")
        params['f_hasta'] = fecha_hasta

    where = " AND ".join(clauses) if clauses else "1=1"
    return where, params


def _ultimas_actualizaciones(s, ids):
    """{reparacion_id: última fecha_cambio} para una lista de ids, en UNA sola
    consulta (evita el N+1 de pedir el historial fila a fila, P1).

    `MAX(fecha_cambio)` equivale a `ORDER BY fecha_cambio DESC LIMIT 1` porque
    los timestamps son strings ordenables 'YYYY-MM-DD HH:MM:SS'. Scoped por
    taller vía el filtro automático del ORM (RepairHistorial es entidad).
    """
    if not ids:
        return {}
    filas = s.execute(
        select(RepairHistorial.reparacion_id, func.max(RepairHistorial.fecha_cambio))
        .where(RepairHistorial.reparacion_id.in_(ids))
        .group_by(RepairHistorial.reparacion_id)
    ).all()
    return {rid: fecha for rid, fecha in filas}
