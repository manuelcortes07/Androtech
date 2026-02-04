"""
Generador de PDFs para AndroTech
Módulo para crear presupuestos de reparación en PDF usando ReportLab
Diseño profesional con tablas, colores corporativos y jerarquía visual
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime
import os


# Colores corporativos
PRIMARY = colors.HexColor("#0d6efd")
SECONDARY = colors.HexColor("#6c757d")
TEXT = colors.HexColor("#212529")
LIGHT_BG = colors.HexColor("#f1f3f5")
WHITE = colors.white
BORDER = colors.HexColor("#dee2e6")

# Configuración fiscal
IVA_PORCENTAJE = 0.21  # 21% de IVA


def generar_presupuesto_pdf(reparacion_data, tipo_documento="presupuesto"):
    """
    Genera un PDF profesional de presupuesto o factura para una reparación.
    
    Args:
        reparacion_data: Dict con keys:
            - id, dispositivo, estado, fecha_entrada, precio
            - descripcion, cliente_nombre, cliente_telefono
        tipo_documento: "presupuesto" o "factura" (default: presupuesto)
    
    Returns:
        BytesIO: Buffer con el PDF generado
    """
    
    # Configurar textos según tipo de documento
    if tipo_documento == "factura":
        titulo_documento = "FACTURA"
        subtitulo_documento = "Documento de facturación"
        numero_prefijo = "F"
        texto_legal = "Factura válida según normativa vigente"
    else:
        titulo_documento = "PRESUPUESTO"
        subtitulo_documento = "Presupuesto sin compromiso"
        numero_prefijo = "P"
        texto_legal = "Este presupuesto no es vinculante y es válido por 30 días"
    
    buffer = BytesIO()
    
    # Configurar documento con márgenes profesionales
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.2*cm,
        leftMargin=1.2*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )
    
    # Estilos personalizados
    styles = getSampleStyleSheet()
    
    style_empresa = ParagraphStyle(
        'Empresa',
        parent=styles['Heading1'],
        fontSize=26,
        textColor=PRIMARY,
        fontName='Helvetica-Bold',
        spaceAfter=2
    )
    
    style_subtitulo = ParagraphStyle(
        'Subtitulo',
        parent=styles['Normal'],
        fontSize=11,
        textColor=SECONDARY,
        fontName='Helvetica',
        spaceAfter=12
    )
    
    style_titulo_seccion = ParagraphStyle(
        'TituloSeccion',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=TEXT,
        fontName='Helvetica-Bold',
        spaceAfter=8,
        spaceBefore=8
    )
    
    style_label = ParagraphStyle(
        'Label',
        parent=styles['Normal'],
        fontSize=9,
        textColor=SECONDARY,
        fontName='Helvetica-Bold'
    )
    
    style_valor = ParagraphStyle(
        'Valor',
        parent=styles['Normal'],
        fontSize=10,
        textColor=TEXT,
        fontName='Helvetica'
    )
    
    # CONTENIDO
    elementos = []
    
    # === CABECERA ===
    tabla_cabecera = []
    
    logo_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'imagenes', 'logo.jpg')
    
    if os.path.exists(logo_path):
        try:
            img = Image(logo_path, width=1*cm, height=1*cm)
            tabla_cabecera.append([
                img,
                Paragraph("<b>ANDROTECH</b><br/><font size=9 color='#6c757d'>Taller de Reparación</font>", style_empresa)
            ])
        except:
            tabla_cabecera.append([Paragraph("<b>ANDROTECH</b>", style_empresa)])
    else:
        tabla_cabecera.append([Paragraph("<b>ANDROTECH</b>", style_empresa)])
    
    table_cabecera = Table(tabla_cabecera, colWidths=[1.2*cm, 15*cm])
    table_cabecera.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (1, 0), (1, 0), 0.5*cm),
    ]))
    elementos.append(table_cabecera)
    elementos.append(Spacer(1, 0.3*cm))
    
    # Línea separadora
    elementos.append(Table([['']]*1, colWidths=[18*cm], rowHeights=[1]))
    tabla_linea = elementos[-1]
    tabla_linea.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (0, 0), 1.5, PRIMARY),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    elementos.append(Spacer(1, 0.3*cm))
    
    # Título del documento
    elementos.append(Paragraph(titulo_documento, style_titulo_seccion))
    elementos.append(Paragraph(f"<font size=9 color='#6c757d'>{subtitulo_documento}</font>", style_valor))
    elementos.append(Spacer(1, 0.2*cm))
    
    # Datos del documento (Nº y fecha)
    id_reparacion = reparacion_data.get('id', 'N/A')
    numero_documento = f"{numero_prefijo}-{id_reparacion:05d}" if isinstance(id_reparacion, int) else f"{numero_prefijo}-{id_reparacion}"
    
    doc_data = [
        [f'Nº de {titulo_documento}:', numero_documento],
        ['Fecha:', datetime.now().strftime("%d/%m/%Y")],
    ]
    
    table_doc = Table(doc_data, colWidths=[4*cm, 4*cm])
    table_doc.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), SECONDARY),
        ('TEXTCOLOR', (1, 0), (1, -1), TEXT),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elementos.append(table_doc)
    elementos.append(Spacer(1, 0.4*cm))
    
    # === DATOS DEL CLIENTE ===
    elementos.append(Paragraph("CLIENTE", style_titulo_seccion))
    
    cliente_data = [
        ['Nombre:', reparacion_data.get('cliente_nombre', 'N/A')],
        ['Teléfono:', reparacion_data.get('cliente_telefono', 'N/A')],
    ]
    
    table_cliente = Table(cliente_data, colWidths=[4*cm, 10*cm])
    table_cliente.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), LIGHT_BG),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), SECONDARY),
        ('TEXTCOLOR', (1, 0), (1, -1), TEXT),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
    ]))
    elementos.append(table_cliente)
    elementos.append(Spacer(1, 0.4*cm))
    
    # === TABLA DE DETALLES ===
    elementos.append(Paragraph("DETALLES DE LA REPARACIÓN", style_titulo_seccion))
    
    detalles_data = [
        ['Concepto', 'Estado', 'Fecha Entrada', 'Precio'],
        [
            reparacion_data.get('dispositivo', 'N/A'),
            reparacion_data.get('estado', 'N/A'),
            reparacion_data.get('fecha_entrada', 'N/A'),
            f"{reparacion_data.get('precio', 0):.2f}€"
        ]
    ]
    
    table_detalles = Table(detalles_data, colWidths=[6*cm, 4*cm, 4*cm, 3*cm])
    table_detalles.setStyle(TableStyle([
        # Cabecera
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        
        # Datos
        ('BACKGROUND', (0, 1), (-1, -1), LIGHT_BG),
        ('TEXTCOLOR', (0, 1), (-1, -1), TEXT),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ALIGN', (2, 1), (-1, -1), 'CENTER'),
        ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),
        
        # Bordes y padding
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elementos.append(table_detalles)
    elementos.append(Spacer(1, 0.4*cm))
    
    # === DESCRIPCIÓN (si existe) ===
    if reparacion_data.get('descripcion'):
        elementos.append(Paragraph("NOTAS", style_titulo_seccion))
        elementos.append(Paragraph(
            str(reparacion_data.get('descripcion', 'Sin notas')),
            style_valor
        ))
        elementos.append(Spacer(1, 0.4*cm))
    
    # === CÁLCULO ECONÓMICO ===
    elementos.append(Spacer(1, 0.3*cm))
    elementos.append(Paragraph("RESUMEN ECONÓMICO", style_titulo_seccion))
    
    # Obtener precio base
    precio_base = reparacion_data.get('precio', 0)
    if isinstance(precio_base, (int, float)):
        base_imponible = float(precio_base)
    else:
        try:
            base_imponible = float(precio_base)
        except (ValueError, TypeError):
            base_imponible = 0.0
    
    # Calcular IVA y total
    iva_importe = round(base_imponible * IVA_PORCENTAJE, 2)
    total_con_iva = round(base_imponible + iva_importe, 2)
    
    # Tabla económica profesional
    tabla_precios_data = [
        ["Concepto", "Importe (€)"],
        ["Base imponible", f"{base_imponible:.2f}"],
        ["IVA (21%)", f"{iva_importe:.2f}"],
        ["TOTAL", f"{total_con_iva:.2f}"],
    ]
    
    tabla_precios = Table(tabla_precios_data, colWidths=[9*cm, 3*cm])
    tabla_precios.setStyle(TableStyle([
        # Cabecera
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        
        # Total (última fila)
        ('BACKGROUND', (0, -1), (-1, -1), LIGHT_BG),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 11),
        ('TEXTCOLOR', (0, -1), (-1, -1), PRIMARY),
        
        # Filas normales
        ('BACKGROUND', (0, 1), (-1, -2), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), TEXT),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        
        # Alineaciones
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        
        # Bordes
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        
        # Padding
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    
    elementos.append(tabla_precios)
    elementos.append(Spacer(1, 0.3*cm))
    
    # Nota legal según tipo de documento
    if tipo_documento == "factura":
        nota_legal = "<b>Importe con IVA incluido.</b> Factura válida para uso contable."
    else:
        nota_legal = "<b>Importe orientativo.</b> El IVA se aplicará en la factura final."
    
    elementos.append(Paragraph(
        f"<font size=8 color='#6c757d'>{nota_legal}</font>",
        style_valor
    ))
    elementos.append(Spacer(1, 0.5*cm))
    
    # === PIE DE PÁGINA ===
    pie_html = f"""
    <font size="8" color="#6c757d">
    <br/>
    <b>Gracias por confiar en ANDROTECH</b><br/>
    <b>{texto_legal}</b><br/>
    Fecha de generación: {datetime.now().strftime("%d/%m/%Y %H:%M")}<br/>
    Proyecto académico 2º SMR
    </font>
    """
    elementos.append(Paragraph(pie_html, style_valor))
    
    # Construir PDF
    doc.build(elementos)
    buffer.seek(0)
    return buffer

