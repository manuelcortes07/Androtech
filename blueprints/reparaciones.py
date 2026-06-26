"""Blueprint de reparaciones (refactor B1) — el dominio más acoplado.

Listado/filtros, ficha (editar_reparacion), alta, estados+historial, fotos,
firma (base64), notas, código de seguimiento, calendario, ticket QR, PDF de
presupuesto y export CSV. Comportamiento idéntico al de app.py; sólo cambian los
nombres de endpoint (reparaciones.<func>). Validación de imágenes (magic bytes,
sin SVG, 5 MB) intacta vía uploads.py.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import secrets
import urllib.parse
from datetime import datetime
from io import BytesIO, StringIO

from flask import (
    Blueprint,
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
from sqlalchemy import select

import uploads
from alerts import calcular_alertas_reparacion
from auth import login_required, permiso_requerido
from avisos import avisar_cambio_estado
from branding import taller_branding
from csv_utils import (
    _SEP_CSV,
    _csv_empresa_header,
    _csv_filename_prefix,
    _csv_pie,
    _fmt_fecha_csv,
    _fmt_precio_csv,
)
from database import get_session
from historial import registrar_cambio_estado, validar_transicion
from models import (
    Cliente,
    FotoReparacion,
    InventarioPieza,
    NotaReparacion,
    PiezaReparacion,
    RepairHistorial,
    Reparacion,
)
from pagination import paginar
from query_helpers import _ultimas_actualizaciones, build_reparaciones_filters
from services import notificador
from uploads import MAX_CONTENT_LENGTH, allowed_file, es_imagen_valida
from utils.pdf_generator import generar_presupuesto_pdf
from utils.security import csrf_protect, validar_precio

logger = logging.getLogger("androtech")

bp = Blueprint("reparaciones", __name__)


# ==============================
# Endpoint: Export reparaciones (filtrado)
# ==============================
@bp.route('/export/reparaciones', methods=['GET'])
@login_required
def export_reparaciones():
    # Permitir admin o recepcionista
    rol = session.get('rol')
    if rol not in ('admin', 'recepcionista'):
        flash('No tienes permisos para exportar datos.', 'danger')
        return redirect(url_for('reparaciones.reparaciones'))

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


@bp.route("/exportar/reparaciones.csv")
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
@bp.route("/reparaciones")
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
@bp.route("/reparaciones/nueva", methods=["GET", "POST"])
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
                return redirect(url_for('reparaciones.nueva_reparacion'))
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

        return redirect(url_for("reparaciones.reparaciones"))

    with get_session() as s:
        clientes = s.scalars(select(Cliente)).all()

    return render_template("nueva_reparacion.html", clientes=clientes)


# EDITAR REPARACIÓN
@bp.route("/reparaciones/editar/<int:id>", methods=["GET", "POST"])
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
                return redirect(url_for('reparaciones.editar_reparacion', id=id))

            # precio validación: solo admin puede cambiar precio
            if precio:
                if not validar_precio(precio):
                    flash('Precio inválido', 'danger')
                    return redirect(url_for('reparaciones.editar_reparacion', id=id))
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

        # Aviso automático al cliente del cambio de estado (efecto secundario,
        # nunca tumba la operación). El punto único `avisos.avisar_cambio_estado`
        # aplica las guardas (estado cambió / hay email / no de baja / taller con
        # avisos activos) y usa el branding del taller dueño. Multi-tenant: el
        # email lo construye el Notificador con g.taller_id de ESTA petición.
        avisar_cambio_estado(
            reparacion_id=id,
            cliente_email=cliente_email,
            cliente_nombre=cliente_nombre,
            estado_anterior=estado_anterior,
            estado_nuevo=estado,
            dispositivo=dispositivo,
            descripcion=descripcion,
        )

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
        return redirect(url_for("reparaciones.reparaciones"))

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
@bp.route("/reparaciones/borrar/<int:id>")
@login_required
@permiso_requerido('reparaciones_borrar')
def borrar_reparacion(id):
    with get_session() as s:
        rep = s.get(Reparacion, id)

        # Validar que no esté pagada
        if rep and rep.estado_pago == 'Pagado':
            flash('❌ No se puede eliminar: esta reparación ya está pagada.', 'danger')
            return redirect(url_for("reparaciones.reparaciones"))

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
    return redirect(url_for("reparaciones.reparaciones"))


# SUBIR FOTOS A REPARACIÓN
@bp.route("/reparaciones/<int:id>/fotos", methods=["POST"])
@login_required
@csrf_protect
def subir_fotos_reparacion(id):
    with get_session() as s:
        rep = s.get(Reparacion, id)
        if not rep:
            flash('Reparación no encontrada.', 'danger')
            return redirect(url_for('reparaciones.reparaciones'))

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
    return redirect(url_for('reparaciones.editar_reparacion', id=id))


# ELIMINAR FOTO DE REPARACIÓN
@bp.route("/reparaciones/fotos/<int:foto_id>/eliminar", methods=["POST"])
@login_required
@csrf_protect
def eliminar_foto_reparacion(foto_id):
    with get_session() as s:
        foto = s.get(FotoReparacion, foto_id)
        if not foto:
            flash('Foto no encontrada.', 'danger')
            return redirect(url_for('reparaciones.reparaciones'))

        reparacion_id = foto.reparacion_id

        # Eliminar archivo físico
        filepath = os.path.join(uploads.UPLOAD_FOLDER, foto.filename)
        if os.path.exists(filepath):
            os.remove(filepath)

        s.delete(foto)
        s.commit()
    flash('Foto eliminada correctamente.', 'success')
    return redirect(url_for('reparaciones.editar_reparacion', id=reparacion_id))


# FIRMA DIGITAL DEL CLIENTE
@bp.route("/reparaciones/<int:id>/firma", methods=["GET"])
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
        return redirect(url_for('reparaciones.reparaciones'))
    return render_template("firmar_reparacion.html", reparacion=reparacion)


@bp.route("/reparaciones/<int:id>/firma", methods=["POST"])
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
@bp.route("/reparaciones/<int:id>/notas", methods=["POST"])
@login_required
@csrf_protect
def agregar_nota_reparacion(id):
    with get_session() as s:
        rep = s.get(Reparacion, id)
        if not rep:
            flash('Reparación no encontrada.', 'danger')
            return redirect(url_for('reparaciones.reparaciones'))

        contenido = request.form.get('contenido', '').strip()
        if not contenido:
            flash('La nota no puede estar vacía.', 'warning')
            return redirect(url_for('reparaciones.editar_reparacion', id=id))

        es_importante = 1 if request.form.get('es_importante') else 0

        s.add(NotaReparacion(
            reparacion_id=id, usuario=session.get('usuario'),
            contenido=contenido,
            fecha_creacion=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            es_importante=es_importante,
        ))
        s.commit()
    flash('Nota agregada correctamente.', 'success')
    return redirect(url_for('reparaciones.editar_reparacion', id=id))


@bp.route("/reparaciones/notas/<int:nota_id>/eliminar", methods=["POST"])
@login_required
@csrf_protect
def eliminar_nota_reparacion(nota_id):
    with get_session() as s:
        nota = s.get(NotaReparacion, nota_id)
        if not nota:
            flash('Nota no encontrada.', 'danger')
            return redirect(url_for('reparaciones.reparaciones'))

        reparacion_id = nota.reparacion_id
        # Solo el autor o admin pueden eliminar
        if nota.usuario != session.get('usuario') and session.get('rol') != 'admin':
            flash('No tienes permiso para eliminar esta nota.', 'danger')
            return redirect(url_for('reparaciones.editar_reparacion', id=reparacion_id))

        s.delete(nota)
        s.commit()
    flash('Nota eliminada.', 'success')
    return redirect(url_for('reparaciones.editar_reparacion', id=reparacion_id))


# ── CALENDARIO DE REPARACIONES ─────────────────────────────────────

@bp.route("/calendario")
@login_required
def calendario():
    return render_template("calendario.html")


@bp.route("/api/calendario/eventos")
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

@bp.route("/reparaciones/<int:id>/ticket")
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
        return redirect(url_for('reparaciones.reparaciones'))

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


# GENERAR PDF PRESUPUESTO
@bp.route("/reparaciones/pdf/<int:id>")
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
            return redirect(url_for('reparaciones.reparaciones'))

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
