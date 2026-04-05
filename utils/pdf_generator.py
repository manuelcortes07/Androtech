"""
PDF Generator - AndroTech
Generador profesional de presupuestos y facturas PDF con diseno corporativo.
Adaptado para taller de reparacion de dispositivos moviles en Huelva, España.
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode.qr import QrCodeWidget
from io import BytesIO

logger = logging.getLogger(__name__)

# Colores corporativos AndroTech
AT_PRIMARY = colors.HexColor('#2B8AC4')
AT_DARK = colors.HexColor('#0F1923')
AT_LIGHT = colors.HexColor('#EBF5FB')
AT_SUCCESS = colors.HexColor('#198754')
AT_GRAY = colors.HexColor('#6c757d')
AT_BORDER = colors.HexColor('#dee2e6')

# Datos de la empresa
COMPANY = {
    'name': 'AndroTech',
    'tagline': 'Taller de Reparacion de Dispositivos Moviles',
    'address': 'Huelva, España',
    'phone': '+34 633 234 395',
    'email': 'manuelcortescontreras11@gmail.com',
    'web': 'AndroTech',
    'iva_rate': 0.21,
}


def _get_styles():
    """Configurar estilos del documento."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name='ATTitle', parent=styles['Heading1'], fontSize=22,
        textColor=AT_PRIMARY, alignment=TA_CENTER, spaceAfter=5
    ))
    styles.add(ParagraphStyle(
        name='ATSub', parent=styles['Normal'], fontSize=10,
        textColor=AT_GRAY, alignment=TA_CENTER, spaceAfter=20
    ))
    styles.add(ParagraphStyle(
        name='ATSection', parent=styles['Heading2'], fontSize=13,
        textColor=AT_DARK, spaceAfter=10
    ))
    styles.add(ParagraphStyle(
        name='ATSmall', parent=styles['Normal'], fontSize=8,
        textColor=AT_GRAY, alignment=TA_CENTER
    ))
    styles.add(ParagraphStyle(
        name='ATFooter', parent=styles['Normal'], fontSize=8,
        textColor=colors.HexColor('#9ba5b0'), alignment=TA_CENTER
    ))
    return styles


def _build_header(styles, doc_type="PRESUPUESTO", doc_number=""):
    """Construir cabecera del documento."""
    elements = []

    # Titulo
    elements.append(Paragraph("AndroTech", styles['ATTitle']))
    elements.append(Paragraph(COMPANY['tagline'], styles['ATSub']))

    # Tipo de documento y numero
    header_data = [
        [doc_type, f'N. {doc_number}'],
        ['Fecha:', datetime.now().strftime('%d/%m/%Y')],
    ]
    header_table = Table(header_data, colWidths=[8.5 * cm, 8.5 * cm])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), AT_PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TEXTCOLOR', (0, 1), (-1, -1), AT_GRAY),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 15))
    return elements


def _build_client_info(styles, cliente):
    """Construir seccion de datos del cliente."""
    elements = []
    elements.append(Paragraph("Datos del Cliente", styles['ATSection']))

    info_data = [
        ['Nombre:', cliente.get('nombre', '—')],
        ['Telefono:', cliente.get('telefono', '—') or '—'],
        ['Email:', cliente.get('email', '—') or '—'],
        ['Direccion:', cliente.get('direccion', '—') or '—'],
    ]
    info_table = Table(info_data, colWidths=[3.5 * cm, 13.5 * cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('TEXTCOLOR', (0, 0), (0, -1), AT_PRIMARY),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, AT_BORDER),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))
    return elements


def _build_device_info(styles, reparacion):
    """Construir seccion de datos del dispositivo."""
    elements = []
    elements.append(Paragraph("Dispositivo", styles['ATSection']))

    device_data = [
        ['Dispositivo:', reparacion.get('dispositivo', '—')],
        ['Descripcion:', reparacion.get('descripcion', '—') or '—'],
        ['Estado:', reparacion.get('estado', '—')],
        ['Fecha Entrada:', reparacion.get('fecha_entrada', '—') or '—'],
    ]
    device_table = Table(device_data, colWidths=[3.5 * cm, 13.5 * cm])
    device_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('TEXTCOLOR', (0, 0), (0, -1), AT_DARK),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, AT_BORDER),
    ]))
    elements.append(device_table)
    elements.append(Spacer(1, 12))
    return elements


def _build_services_table(styles, servicios, piezas=None):
    """Construir tabla de servicios/piezas."""
    elements = []
    elements.append(Paragraph("Detalle de Servicios", styles['ATSection']))

    headers = ['Concepto', 'Cant.', 'Precio Unit.', 'Subtotal']
    table_data = [headers]

    for s in servicios:
        qty = s.get('cantidad', 1)
        unit = s.get('precio', 0)
        sub = qty * unit
        table_data.append([
            s.get('descripcion', 'Reparacion'),
            str(qty),
            f'{unit:.2f} EUR',
            f'{sub:.2f} EUR'
        ])

    # Anadir piezas si existen
    if piezas:
        for p in piezas:
            qty = p.get('cantidad', 1)
            unit = p.get('precio_venta', 0)
            sub = qty * unit
            table_data.append([
                f'Pieza: {p.get("nombre", "")}',
                str(qty),
                f'{unit:.2f} EUR',
                f'{sub:.2f} EUR'
            ])

    svc_table = Table(table_data, colWidths=[8 * cm, 2 * cm, 3.5 * cm, 3.5 * cm])
    svc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), AT_DARK),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, AT_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
    ]))
    elements.append(svc_table)
    elements.append(Spacer(1, 12))
    return elements


def _build_totals(styles, subtotal):
    """Construir seccion de totales con IVA."""
    elements = []

    iva = subtotal * COMPANY['iva_rate']
    total = subtotal + iva

    totals_data = [
        ['Base Imponible:', f'{subtotal:.2f} EUR'],
        [f'IVA ({int(COMPANY["iva_rate"] * 100)}%):', f'{iva:.2f} EUR'],
        ['TOTAL:', f'{total:.2f} EUR'],
    ]

    totals_table = Table(totals_data, colWidths=[12.5 * cm, 4.5 * cm])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 13),
        ('BACKGROUND', (0, -1), (-1, -1), AT_SUCCESS),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
        ('LINEABOVE', (0, 0), (-1, 0), 1, AT_BORDER),
    ]))
    elements.append(totals_table)
    elements.append(Spacer(1, 15))
    return elements


def _build_terms(styles, tipo="presupuesto"):
    """Construir terminos y condiciones."""
    elements = []
    elements.append(Paragraph("Terminos y Condiciones", styles['ATSection']))

    if tipo == "presupuesto":
        terms_text = (
            '<b>1.</b> Este presupuesto tiene una validez de 30 dias naturales.<br/>'
            '<b>2.</b> Los precios pueden variar si se detectan averias adicionales durante la reparacion.<br/>'
            '<b>3.</b> Garantia de 3 meses en piezas y mano de obra.<br/>'
            '<b>4.</b> El dispositivo debe recogerse en un plazo maximo de 30 dias tras la notificacion de finalizacion.<br/>'
            '<b>5.</b> AndroTech no se hace responsable de datos almacenados en el dispositivo.'
        )
    else:
        terms_text = (
            '<b>1.</b> Garantia de 3 meses en piezas y mano de obra desde la fecha de entrega.<br/>'
            '<b>2.</b> La garantia no cubre danos por agua, golpes o manipulacion por terceros.<br/>'
            '<b>3.</b> Conserve esta factura como comprobante de garantia.<br/>'
            '<b>4.</b> AndroTech no se hace responsable de datos almacenados en el dispositivo.'
        )

    terms = Paragraph(terms_text, ParagraphStyle(
        'Terms', parent=styles['Normal'], fontSize=8, textColor=AT_GRAY,
        leading=13
    ))
    elements.append(terms)
    elements.append(Spacer(1, 15))
    return elements


def _build_qr(styles, reparacion_id):
    """Construir QR de consulta."""
    elements = []
    try:
        url = f"http://127.0.0.1:5000/consulta"
        qr = QrCodeWidget(url)
        qr.barWidth = 80
        qr.barHeight = 80
        d = Drawing(90, 90)
        d.add(qr)

        qr_data = [
            [d, Paragraph(
                f'<b>Reparacion #{reparacion_id}</b><br/>'
                f'Escanea el QR para consultar<br/>el estado de tu reparacion',
                ParagraphStyle('QRText', parent=styles['Normal'], fontSize=8,
                               textColor=AT_GRAY, alignment=TA_LEFT)
            )]
        ]
        qr_table = Table(qr_data, colWidths=[3 * cm, 10 * cm])
        qr_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(qr_table)
        elements.append(Spacer(1, 10))
    except Exception as e:
        logger.warning(f"No se pudo generar QR: {e}")
    return elements


def _build_footer(styles):
    """Construir pie de pagina."""
    elements = []
    footer_text = (
        f'<b>{COMPANY["name"]}</b> — {COMPANY["tagline"]}<br/>'
        f'{COMPANY["address"]} | Tel: {COMPANY["phone"]} | {COMPANY["email"]}<br/>'
        f'Documento generado el {datetime.now().strftime("%d/%m/%Y a las %H:%M")}'
    )
    elements.append(Paragraph(footer_text, styles['ATFooter']))
    return elements


def generar_presupuesto_pdf(reparacion_data, tipo_documento="presupuesto"):
    """
    Generar un PDF de presupuesto o factura para una reparacion.

    Args:
        reparacion_data: dict con campos: id, dispositivo, descripcion, estado,
                         precio, fecha_entrada, cliente_nombre, cliente_telefono,
                         cliente_email, cliente_direccion, piezas (opcional)
        tipo_documento: 'presupuesto' o 'factura'

    Returns:
        BytesIO buffer con el PDF generado
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm)
    styles = _get_styles()
    elements = []

    rep_id = reparacion_data.get('id', 0)
    prefix = 'F' if tipo_documento == 'factura' else 'P'
    doc_number = f'{prefix}-{rep_id:05d}'
    doc_title = 'FACTURA' if tipo_documento == 'factura' else 'PRESUPUESTO'

    # Header
    elements.extend(_build_header(styles, doc_title, doc_number))

    # Datos del cliente
    cliente = {
        'nombre': reparacion_data.get('cliente_nombre', '—'),
        'telefono': reparacion_data.get('cliente_telefono', ''),
        'email': reparacion_data.get('cliente_email', ''),
        'direccion': reparacion_data.get('cliente_direccion', ''),
    }
    elements.extend(_build_client_info(styles, cliente))

    # Datos del dispositivo
    elements.extend(_build_device_info(styles, reparacion_data))

    # Servicios
    precio = reparacion_data.get('precio', 0) or 0
    servicios = [{
        'descripcion': f'Reparacion: {reparacion_data.get("dispositivo", "Dispositivo")}',
        'cantidad': 1,
        'precio': precio,
    }]

    # Piezas utilizadas (si las hay)
    piezas = reparacion_data.get('piezas', [])
    elements.extend(_build_services_table(styles, servicios, piezas))

    # Totales
    subtotal_piezas = sum((p.get('cantidad', 1) * p.get('precio_venta', 0)) for p in piezas)
    subtotal = precio + subtotal_piezas
    elements.extend(_build_totals(styles, subtotal))

    # Terminos
    elements.extend(_build_terms(styles, tipo_documento))

    # QR
    elements.extend(_build_qr(styles, rep_id))

    # Footer
    elements.extend(_build_footer(styles))

    doc.build(elements)
    buffer.seek(0)
    return buffer
