"""Blueprint de clientes (refactor B1).

Listado/búsqueda, alta, edición, borrado, historial por cliente (+ PDF), búsqueda
global y export CSV de clientes. Comportamiento idéntico al que tenían en app.py;
sólo cambia el nombre de endpoint (clientes → clientes.clientes, etc.).
"""

from __future__ import annotations

import csv
import logging
import urllib.parse
from datetime import datetime
from io import BytesIO, StringIO

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from sqlalchemy import String, cast, func, or_, select, text

from auth import login_required, permiso_requerido
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
from models import Cliente, Reparacion
from pagination import paginar
from query_helpers import _ultimas_actualizaciones
from services import notificador
from utils.security import csrf_protect

logger = logging.getLogger("androtech")

bp = Blueprint("clientes", __name__)


@bp.route("/clientes")
@login_required
def clientes():
    # Listado paginado server-side (B5) con búsqueda. COUNT y SELECT van
    # auto-scoped al taller por el filtro automático del ORM (g.taller_id), así
    # que el contador y las filas son SIEMPRE del taller. La búsqueda es
    # server-side para que funcione sobre TODO el conjunto, no sólo la página.
    q = request.args.get("q", "").strip()
    base = select(Cliente)
    cnt = select(func.count(Cliente.id))
    if q:
        like = f"%{q}%"
        cond = or_(Cliente.nombre.like(like), Cliente.email.like(like),
                   Cliente.telefono.like(like))
        base = base.where(cond)
        cnt = cnt.where(cond)
    with get_session() as s:
        total = s.scalar(cnt)
        pag = paginar(total)
        clientes = s.scalars(
            base.order_by(Cliente.nombre).limit(pag.per_page).offset(pag.offset)
        ).all()
    filters_query = urllib.parse.urlencode({"q": q}) if q else ""
    return render_template("clientes.html", clientes=clientes, pagina=pag,
                           q=q, filters_query=filters_query)


# CREAR CLIENTE
@bp.route("/clientes/nuevo", methods=["GET", "POST"])
@login_required
@csrf_protect
def nuevo_cliente():
    if request.method == "POST":
        nombre = request.form["nombre"]
        telefono = request.form["telefono"]
        email = request.form["email"]
        direccion = request.form["direccion"]

        with get_session() as s:
            s.add(Cliente(nombre=nombre, telefono=telefono,
                          email=email, direccion=direccion))
            s.commit()

        # Enviar email de bienvenida al nuevo cliente
        if email:
            try:
                notificador.enviar_email("send_bienvenida_cliente",
                    to_email=email,
                    cliente_nombre=nombre
                )
                logger.info(f"Email de bienvenida enviado a {email} para cliente {nombre}")
            except Exception as e:
                logger.error(f"Error enviando email de bienvenida: {type(e).__name__}: {str(e)}")

        return redirect(url_for("clientes.clientes"))

    return render_template("nuevo_cliente.html")


# EDITAR CLIENTE
@bp.route("/clientes/editar/<int:id>", methods=["GET", "POST"])
@login_required
@csrf_protect
def editar_cliente(id):
    if request.method == "POST":
        nombre = request.form["nombre"]
        telefono = request.form["telefono"]
        email = request.form["email"]
        direccion = request.form["direccion"]

        with get_session() as s:
            cliente = s.get(Cliente, id)
            if cliente:
                cliente.nombre = nombre
                cliente.telefono = telefono
                cliente.email = email
                cliente.direccion = direccion
                s.commit()

        return redirect(url_for("clientes.clientes"))

    with get_session() as s:
        cliente = s.get(Cliente, id)

    return render_template("editar_cliente.html", cliente=cliente)


# HISTORIAL CLIENTE - SOLO ADMIN
@bp.route("/cliente/historial")
@login_required
@permiso_requerido('clientes_historial')
def historial_cliente():
    # Fase 2.4: raw SQL → filtro MANUAL de taller en cada query.
    tp = {"tid": g.taller_id}
    s = get_session()

    # Estadísticas generales
    total_reparaciones = s.execute(text("SELECT COUNT(*) FROM reparaciones WHERE taller_id = :tid"), tp).scalar()
    pagadas = s.execute(text("SELECT COUNT(*) FROM reparaciones WHERE taller_id = :tid AND estado_pago = 'Pagado'"), tp).scalar()
    pendientes = s.execute(text("SELECT COUNT(*) FROM reparaciones WHERE taller_id = :tid AND estado_pago != 'Pagado'"), tp).scalar()
    total_invertido = s.execute(text("SELECT COALESCE(SUM(precio), 0) FROM reparaciones WHERE taller_id = :tid AND precio IS NOT NULL"), tp).scalar()
    promedio_precio = s.execute(text("SELECT COALESCE(AVG(precio), 0) FROM reparaciones WHERE taller_id = :tid AND precio IS NOT NULL"), tp).scalar()
    total_completadas = s.execute(text("SELECT COUNT(*) FROM reparaciones WHERE taller_id = :tid AND (estado = 'Terminado' OR estado = 'Entregado')"), tp).scalar()

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
    # El filtro de taller SIEMPRE está presente; los filtros de la UI se añaden encima.
    where = ["reparaciones.taller_id = :tid"]
    params = {"tid": g.taller_id}
    if estado_filtro:
        where.append("reparaciones.estado = :estado")
        params['estado'] = estado_filtro
    if cliente_filtro:
        where.append("reparaciones.cliente_id = :cliente_id")
        params['cliente_id'] = cliente_filtro

    where_clause = " WHERE " + " AND ".join(where)

    total_count = s.execute(
        text("SELECT COUNT(*) FROM reparaciones" + where_clause), params
    ).scalar()
    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

    reparaciones_rows = s.execute(
        text(base_sql + where_clause + " ORDER BY reparaciones.id DESC LIMIT :limit OFFSET :offset"),
        {**params, 'limit': per_page, 'offset': offset},
    ).mappings().all()
    reparaciones = [dict(r) for r in reparaciones_rows]

    # Enriquecer con la última actualización SIN N+1: una consulta agregada (P1).
    ultimas = _ultimas_actualizaciones(s, [r['id'] for r in reparaciones])
    reparaciones_enriquecidas = []
    for r in reparaciones:
        r['ultima_actualizacion'] = ultimas.get(r['id'])
        reparaciones_enriquecidas.append(r)

    estados = s.execute(text("SELECT DISTINCT estado FROM reparaciones WHERE taller_id = :tid ORDER BY estado"), tp).all()
    clientes = s.scalars(select(Cliente).order_by(Cliente.nombre)).all()

    s.close()

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
@bp.route("/cliente/<int:id>/historial-pdf")
@login_required
def exportar_historial_cliente_pdf(id):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    with get_session() as s:
        cliente = s.get(Cliente, id)
    if not cliente:
        flash('Cliente no encontrado.', 'danger')
        return redirect(url_for('clientes.clientes'))

    with get_session() as s:
        # ⚠️ select(Model.__table__) es Core → el filtro automático NO se aplica.
        # Filtro de taller MANUAL obligatorio (Fase 2.5).
        reparaciones = s.execute(
            select(Reparacion.__table__)
            .where(Reparacion.__table__.c.cliente_id == id)
            .where(Reparacion.__table__.c.taller_id == g.taller_id)
            .order_by(Reparacion.__table__.c.fecha_entrada.desc())
        ).mappings().all()

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

    # Header — emisor = taller activo (no la marca de la plataforma)
    _marca = taller_branding()
    elements.append(Paragraph(_marca['nombre'] or 'Taller', styles['ATTitle']))
    elements.append(Paragraph("Historial de Reparaciones del Cliente", styles['ATSub']))

    # Client info
    elements.append(Paragraph("Datos del Cliente", styles['ATSection']))
    info_data = [
        ['Nombre:', cliente.nombre],
        ['Email:', cliente.email or '—'],
        ['Teléfono:', cliente.telefono or '—'],
        ['Dirección:', cliente.direccion or '—'],
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
    _pie = ' · '.join(filter(None, [_marca['nombre'] or 'Taller',
                                    _marca['direccion'], _marca['telefono']]))
    elements.append(Paragraph(
        f'<para alignment="center"><font size="8" color="#9ba5b0">'
        f'Generado el {datetime.now().strftime("%d/%m/%Y %H:%M")} — {_pie}'
        f'</font></para>', styles['Normal']
    ))

    doc.build(elements)
    buffer.seek(0)

    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f'historial_{cliente.nombre.replace(" ", "_")}_{datetime.now().strftime("%Y%m%d")}.pdf')


# BORRAR CLIENTE
@bp.route("/clientes/borrar/<int:id>")
@login_required
@permiso_requerido('clientes_borrar')
def borrar_cliente(id):
    with get_session() as s:
        cliente = s.get(Cliente, id)
        if not cliente:
            return redirect(url_for("clientes.clientes"))
        # C1 — DECISIÓN DE PRODUCTO: IMPEDIR borrar un cliente con reparaciones.
        # Más seguro que el cascada: no se pierde el historial de reparaciones
        # (registro valioso) por borrar una ficha de cliente. Además evita la
        # violación de FK en Postgres (reparaciones.cliente_id NO es cascade, a
        # propósito). El conteo va auto-scoped al taller (Reparacion con scope).
        n = s.scalar(
            select(func.count(Reparacion.id)).where(Reparacion.cliente_id == id)
        )
        if n:
            flash(f"No se puede eliminar: este cliente tiene {n} reparación(es). "
                  "Bórralas o reasígnalas primero.", "danger")
            return redirect(url_for("clientes.clientes"))
        s.delete(cliente)
        s.commit()
    flash("Cliente eliminado.", "success")
    return redirect(url_for("clientes.clientes"))


# =========================================
#  🔸 BÚSQUEDA GLOBAL
# =========================================
@bp.route("/buscar")
@login_required
def buscar():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        flash('Introduce al menos 2 caracteres para buscar.', 'warning')
        return redirect(url_for('dashboard.dashboard'))

    like = f'%{q}%'

    with get_session() as s:
        clientes_result = s.scalars(
            select(Cliente).where(
                Cliente.nombre.like(like)
                | Cliente.email.like(like)
                | Cliente.telefono.like(like)
            ).limit(20)
        ).all()

        reparaciones_result = s.execute(
            select(
                Reparacion.id, Reparacion.dispositivo, Reparacion.estado,
                Reparacion.estado_pago, Reparacion.precio,
                Reparacion.fecha_entrada, Cliente.nombre.label('cliente'),
            )
            .join(Cliente, Reparacion.cliente_id == Cliente.id)
            .where(
                Reparacion.dispositivo.like(like)
                | Reparacion.descripcion.like(like)
                | Cliente.nombre.like(like)
                | (cast(Reparacion.id, String) == q)
            )
            .order_by(Reparacion.id.desc())
            .limit(20)
        ).mappings().all()

    return render_template("buscar.html",
        q=q,
        clientes=clientes_result,
        reparaciones=reparaciones_result
    )


# =========================================
#  🔸 EXPORTAR CSV DE CLIENTES
# =========================================
@bp.route("/exportar/clientes.csv")
@login_required
@permiso_requerido('clientes_exportar')
def exportar_clientes_csv():
    # Fase 2.4: filtro MANUAL de taller. El JOIN a reparaciones lleva también
    # el filtro (r.taller_id = c.taller_id) como red de seguridad adicional.
    with get_session() as s:
        rows = s.execute(text('''
            SELECT c.id, c.nombre, c.email, c.telefono, c.direccion,
                   COUNT(r.id) as total_reparaciones,
                   SUM(CASE WHEN r.estado IN ('Pendiente', 'En proceso') THEN 1 ELSE 0 END) as reparaciones_activas,
                   SUM(CASE WHEN r.estado IN ('Terminado', 'Entregado') THEN 1 ELSE 0 END) as reparaciones_completadas,
                   COALESCE(SUM(r.precio), 0) as total_facturado,
                   COALESCE(SUM(CASE WHEN r.estado_pago = 'Pagado' THEN r.precio ELSE 0 END), 0) as total_pagado,
                   COALESCE(SUM(CASE WHEN r.estado_pago = 'Pendiente' THEN r.precio ELSE 0 END), 0) as total_pendiente,
                   MAX(r.fecha_entrada) as ultima_visita
            FROM clientes c
            LEFT JOIN reparaciones r ON r.cliente_id = c.id AND r.taller_id = c.taller_id
            WHERE c.taller_id = :tid
            GROUP BY c.id
            ORDER BY c.nombre
        '''), {"tid": g.taller_id}).mappings().all()

    total_clientes   = len(rows)
    total_facturado  = sum(r['total_facturado'] or 0 for r in rows)
    total_cobrado    = sum(r['total_pagado']    or 0 for r in rows)
    total_pendiente  = total_facturado - total_cobrado
    clientes_activos = sum(1 for r in rows if (r['reparaciones_activas'] or 0) > 0)

    si = StringIO()
    w  = csv.writer(si, delimiter=';')

    _csv_empresa_header(w, 'INFORME COMPLETO DE CLIENTES')

    w.writerow(['--- RESUMEN ---'])
    w.writerow(['Total clientes',          total_clientes])
    w.writerow(['Clientes con rep. activa', clientes_activos])
    w.writerow(['Total facturado',          _fmt_precio_csv(total_facturado)])
    w.writerow(['Total cobrado',            _fmt_precio_csv(total_cobrado)])
    w.writerow(['Pendiente de cobro',       _fmt_precio_csv(total_pendiente)])
    w.writerow([])

    w.writerow(['--- DETALLE DE CLIENTES ---'])
    w.writerow([
        'N. Cliente', 'Nombre', 'Email', 'Telefono', 'Direccion',
        'Total Reparaciones', 'Reparaciones Activas', 'Reparaciones Completadas',
        'Total Facturado', 'Total Pagado', 'Pendiente',
        'Ultima Visita',
    ])

    for r in rows:
        w.writerow([
            r['id'],
            r['nombre'],
            r['email']         or '',
            r['telefono']      or '',
            r['direccion']     or '',
            r['total_reparaciones'],
            r['reparaciones_activas']    or 0,
            r['reparaciones_completadas'] or 0,
            _fmt_precio_csv(r['total_facturado']),
            _fmt_precio_csv(r['total_pagado']),
            _fmt_precio_csv(r['total_pendiente']),
            _fmt_fecha_csv(r['ultima_visita']) or 'Sin visitas',
        ])

    w.writerow([])
    w.writerow([_SEP_CSV])
    _csv_pie(w)
    w.writerow([_SEP_CSV])

    output = BytesIO()
    output.write(si.getvalue().encode('utf-8-sig'))
    output.seek(0)
    return send_file(output, mimetype='text/csv', as_attachment=True,
                     download_name=f'{_csv_filename_prefix()}_Clientes_{datetime.now().strftime("%Y%m%d_%H%M")}.csv')
