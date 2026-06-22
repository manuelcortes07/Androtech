"""
PDF Generator (Kintsu)
Generador de presupuestos y facturas PDF. El EMISOR del documento es el TALLER
activo (nombre, dirección, contacto, NIF, IVA, logo), nunca una constante: ver
`_emisor()` y el parámetro `taller=` de `generar_presupuesto_pdf`.
"""

import logging
import os
from datetime import datetime
from io import BytesIO

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)

# Colores corporativos AndroTech
AT_PRIMARY = colors.HexColor('#2B8AC4')
AT_DARK = colors.HexColor('#0F1923')
AT_LIGHT = colors.HexColor('#EBF5FB')
AT_SUCCESS = colors.HexColor('#198754')
AT_GRAY = colors.HexColor('#6c757d')
AT_BORDER = colors.HexColor('#dee2e6')

# Valores por defecto SEGUROS del emisor. NO son marca de ningún taller: si un
# taller no ha rellenado sus datos, el documento degrada con estos genéricos
# (nunca "AndroTech" ni "Kintsu"). El nombre real sale del Taller activo.
EMISOR_DEFAULT = {
    'name': 'Taller',
    'tagline': 'Taller de Reparación de Dispositivos',
    'address': '',
    'phone': '',
    'email': '',
    'nif': '',
    'web': '',
    'logo_path': '',
    'iva_rate': 0.21,
}


def _emisor(taller):
    """Funde los datos del `taller` (dict) sobre los defaults seguros."""
    t = taller or {}
    return {
        'name': (t.get('nombre') or '').strip() or EMISOR_DEFAULT['name'],
        'tagline': EMISOR_DEFAULT['tagline'],
        'address': (t.get('direccion') or '').strip(),
        'phone': (t.get('telefono') or '').strip(),
        'email': (t.get('email') or '').strip(),
        'nif': (t.get('nif') or '').strip(),
        'web': (t.get('web') or '').strip(),
        'logo_path': (t.get('logo_path') or '').strip(),
        'iva_rate': float(t.get('iva_rate', EMISOR_DEFAULT['iva_rate'])),
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


def _build_header(styles, doc_type="PRESUPUESTO", doc_number="", emisor=None):
    """Construir cabecera del documento (con los datos del taller emisor)."""
    emisor = emisor or EMISOR_DEFAULT
    elements = []

    # Logo del taller si lo tiene configurado y el fichero existe (degrada sin él).
    logo_path = emisor.get('logo_path')
    if logo_path and os.path.isfile(logo_path):
        try:
            from reportlab.platypus import Image
            elements.append(Image(logo_path, width=3.5 * cm, height=3.5 * cm,
                                  kind='proportional'))
            elements.append(Spacer(1, 4))
        except Exception as e:  # pragma: no cover - logo opcional
            logger.warning(f"No se pudo cargar el logo del taller: {e}")

    # Nombre del taller emisor (NUNCA la marca de la plataforma)
    elements.append(Paragraph(emisor.get('name') or 'Taller', styles['ATTitle']))
    elements.append(Paragraph(emisor.get('tagline') or '', styles['ATSub']))

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


def _build_totals(styles, subtotal, iva_rate=0.21):
    """Construir seccion de totales con IVA (tasa del taller emisor)."""
    elements = []

    iva = subtotal * iva_rate
    total = subtotal + iva

    totals_data = [
        ['Base Imponible:', f'{subtotal:.2f} EUR'],
        [f'IVA ({int(iva_rate * 100)}%):', f'{iva:.2f} EUR'],
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


def _build_terms(styles, tipo="presupuesto", emisor_name="El taller"):
    """Construir terminos y condiciones (el emisor es el taller, no la plataforma)."""
    elements = []
    elements.append(Paragraph("Terminos y Condiciones", styles['ATSection']))

    nombre = emisor_name or "El taller"
    if tipo == "presupuesto":
        terms_text = (
            '<b>1.</b> Este presupuesto tiene una validez de 30 dias naturales.<br/>'
            '<b>2.</b> Los precios pueden variar si se detectan averias adicionales durante la reparacion.<br/>'
            '<b>3.</b> Garantia de 3 meses en piezas y mano de obra.<br/>'
            '<b>4.</b> El dispositivo debe recogerse en un plazo maximo de 30 dias tras la notificacion de finalizacion.<br/>'
            f'<b>5.</b> {nombre} no se hace responsable de datos almacenados en el dispositivo.'
        )
    else:
        terms_text = (
            '<b>1.</b> Garantia de 3 meses en piezas y mano de obra desde la fecha de entrega.<br/>'
            '<b>2.</b> La garantia no cubre danos por agua, golpes o manipulacion por terceros.<br/>'
            '<b>3.</b> Conserve esta factura como comprobante de garantia.<br/>'
            f'<b>4.</b> {nombre} no se hace responsable de datos almacenados en el dispositivo.'
        )

    terms = Paragraph(terms_text, ParagraphStyle(
        'Terms', parent=styles['Normal'], fontSize=8, textColor=AT_GRAY,
        leading=13
    ))
    elements.append(terms)
    elements.append(Spacer(1, 15))
    return elements


def _build_qr(styles, reparacion_id, base_url=None, taller_slug=None, codigo=None):
    """
    Construir QR de consulta directa.

    H3: el QR codifica el CÓDIGO PÚBLICO no adivinable (`?codigo=`), NO el id
    secuencial. Con slug de taller usa la URL canónica `/t/{slug}/consulta?codigo=X`;
    sin slug, `/consulta?codigo=X` (el código resuelve el taller). Si no hubiera
    código (no debería tras el backfill), el QR apunta al formulario `/consulta`.
    base_url se recibe desde la vista Flask (request.host_url).
    """
    elements = []
    try:
        # Fallback por si se llama fuera de contexto de peticion (tests, etc.)
        if not base_url:
            base_url = os.environ.get(
                'APP_BASE_URL', 'https://androtech-production.up.railway.app'
            )
        base = base_url.rstrip('/')
        prefijo = f"/t/{taller_slug}" if taller_slug else ""
        if codigo:
            url = f"{base}{prefijo}/consulta?codigo={codigo}"
        else:
            url = f"{base}{prefijo}/consulta"

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


def _build_footer(styles, emisor=None):
    """Construir pie de pagina con los datos del taller emisor."""
    emisor = emisor or EMISOR_DEFAULT
    # Línea de contacto: sólo los campos que el taller tenga rellenos.
    contacto = ' | '.join(filter(None, [
        emisor.get('address'),
        f"Tel: {emisor['phone']}" if emisor.get('phone') else '',
        emisor.get('email'),
        f"NIF: {emisor['nif']}" if emisor.get('nif') else '',
    ]))
    lineas = [f'<b>{emisor.get("name") or "Taller"}</b> — {emisor.get("tagline") or ""}']
    if contacto:
        lineas.append(contacto)
    lineas.append(f'Documento generado el {datetime.now().strftime("%d/%m/%Y a las %H:%M")} · Hecho con Kintsu')
    elements = [Paragraph('<br/>'.join(lineas), styles['ATFooter'])]
    return elements


def generar_presupuesto_pdf(reparacion_data, tipo_documento="presupuesto", base_url=None,
                            taller_slug=None, taller=None):
    """
    Generar un PDF de presupuesto o factura para una reparacion.

    Args:
        reparacion_data: dict con campos: id, dispositivo, descripcion, estado,
                         precio, fecha_entrada, cliente_nombre, cliente_telefono,
                         cliente_email, cliente_direccion, piezas (opcional)
        tipo_documento: 'presupuesto' o 'factura'
        taller: dict con los datos del TALLER emisor (nombre, direccion, telefono,
                email, nif, iva_rate, logo_path). Si es None o faltan campos, el
                documento degrada a genéricos (nunca "AndroTech"/"Kintsu").

    Returns:
        BytesIO buffer con el PDF generado
    """
    emisor = _emisor(taller)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm)
    styles = _get_styles()
    elements = []

    # rep_id puede llegar como str (p. ej. desde la metadata del webhook de
    # Stripe). Coerción segura a int para el formato :05d (si no, revienta con
    # "Unknown format code 'd' for object of type 'str'").
    try:
        rep_id = int(reparacion_data.get('id', 0))
    except (TypeError, ValueError):
        rep_id = 0
    prefix = 'F' if tipo_documento == 'factura' else 'P'
    doc_number = f'{prefix}-{rep_id:05d}'
    doc_title = 'FACTURA' if tipo_documento == 'factura' else 'PRESUPUESTO'

    # Header
    elements.extend(_build_header(styles, doc_title, doc_number, emisor=emisor))

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
    elements.extend(_build_totals(styles, subtotal, iva_rate=emisor['iva_rate']))

    # Terminos
    elements.extend(_build_terms(styles, tipo_documento, emisor_name=emisor['name']))

    # QR (H3: con el código público, no el id)
    elements.extend(_build_qr(styles, rep_id, base_url=base_url, taller_slug=taller_slug,
                              codigo=reparacion_data.get('codigo_publico')))

    # Footer
    elements.extend(_build_footer(styles, emisor=emisor))

    doc.build(elements)
    buffer.seek(0)
    return buffer
