"""
PDF Invoice Generator - AndroTech
Generador profesional de facturas PDF con diseño corporativo.
Versión avanzada con múltiples servicios, información fiscal completa y templates profesionales.
"""

import os
import logging
import tempfile
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode.qr import QrCodeWidget
from io import BytesIO

logger = logging.getLogger(__name__)

class InvoiceGenerator:
    """Generador profesional de facturas PDF para AndroTech."""

    def __init__(self, template_dir: str = "templates/pdf"):
        """Inicializar el generador de facturas."""
        self.template_dir = template_dir
        self.company_info = {
            'name': 'AndroTech',
            'address': 'Calle 123 #45-67, Bogotá, Colombia',
            'phone': '+57 300 123 4567',
            'email': 'info@androtech.com',
            'website': 'www.androtech.com',
            'nit': '901.234.567-8',
            'logo_path': os.path.join(template_dir, 'logo.png')
        }

        # Crear directorio si no existe
        os.makedirs(template_dir, exist_ok=True)

        # Configurar estilos
        self._setup_styles()

        logger.info("Invoice generator initialized")

    def _setup_styles(self):
        """Configurar estilos de documento."""
        self.styles = getSampleStyleSheet()

        # Estilo para títulos
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#2c3e50'),
            alignment=TA_CENTER,
            spaceAfter=30
        ))

        # Estilo para subtítulos
        self.styles.add(ParagraphStyle(
            name='CustomSubtitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#34495e'),
            alignment=TA_LEFT,
            spaceAfter=15
        ))

        # Estilo para información de empresa
        self.styles.add(ParagraphStyle(
            name='CompanyInfo',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#7f8c8d'),
            alignment=TA_LEFT
        ))

        # Estilo para totales
        self.styles.add(ParagraphStyle(
            name='TotalStyle',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=colors.HexColor('#27ae60'),
            alignment=TA_RIGHT,
            fontName='Helvetica-Bold'
        ))

    def generate_invoice(self, invoice_data: Dict[str, Any], output_path: str) -> bool:
        """
        Generar factura PDF.

        Args:
            invoice_data: Datos de la factura
            output_path: Ruta donde guardar el PDF

        Returns:
            bool: True si se generó correctamente
        """
        try:
            # Crear documento
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=2*cm,
                leftMargin=2*cm,
                topMargin=2*cm,
                bottomMargin=2*cm
            )

            # Construir elementos del documento
            elements = []

            # Header con logo e información de empresa
            elements.extend(self._build_header())

            # Información del cliente y factura
            elements.extend(self._build_invoice_info(invoice_data))

            # Tabla de servicios
            elements.extend(self._build_services_table(invoice_data))

            # Totales
            elements.extend(self._build_totals(invoice_data))

            # Términos y condiciones
            elements.extend(self._build_terms())

            # QR de consulta
            reparacion_id = invoice_data.get('reparacion_id')
            if reparacion_id:
                consulta_url = f"https://androtech.es/consulta?id={reparacion_id}"
                elements.extend(self._build_qr_code(consulta_url))

            # Footer
            elements.extend(self._build_footer())

            # Generar PDF
            doc.build(elements)

            logger.info(f"Invoice PDF generated successfully: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to generate invoice PDF: {str(e)}")
            return False

    def _build_header(self) -> List[Any]:
        """Construir header del documento."""
        elements = []

        # Logo (si existe)
        if os.path.exists(self.company_info['logo_path']):
            try:
                logo = Image(self.company_info['logo_path'], 2*inch, 1*inch)
                elements.append(logo)
                elements.append(Spacer(1, 20))
            except:
                pass  # Si no hay logo, continuar sin él

        # Nombre de la empresa
        title = Paragraph("AndroTech", self.styles['CustomTitle'])
        elements.append(title)

        # Información de contacto
        contact_info = f"""
        <b>Dirección:</b> {self.company_info['address']}<br/>
        <b>Teléfono:</b> {self.company_info['phone']}<br/>
        <b>Email:</b> {self.company_info['email']}<br/>
        <b>Sitio Web:</b> {self.company_info['website']}<br/>
        <b>NIT:</b> {self.company_info['nit']}
        """
        contact = Paragraph(contact_info, self.styles['CompanyInfo'])
        elements.append(contact)
        elements.append(Spacer(1, 30))

        return elements

    def _build_invoice_info(self, invoice_data: Dict[str, Any]) -> List[Any]:
        """Construir información de factura y cliente."""
        elements = []

        # Título de factura
        invoice_title = Paragraph("FACTURA ELECTRÓNICA", self.styles['CustomSubtitle'])
        elements.append(invoice_title)

        # Información de factura
        invoice_info = [
            ['Número de Factura:', invoice_data.get('invoice_number', 'N/A')],
            ['Fecha de Emisión:', invoice_data.get('date', datetime.now().strftime('%Y-%m-%d'))],
            ['Fecha de Vencimiento:', invoice_data.get('due_date', 'Inmediato')],
            ['Cliente:', invoice_data.get('customer_name', 'N/A')],
            ['Identificación:', invoice_data.get('customer_id', 'N/A')],
            ['Dirección:', invoice_data.get('customer_address', 'N/A')],
            ['Teléfono:', invoice_data.get('customer_phone', 'N/A')],
            ['Email:', invoice_data.get('customer_email', 'N/A')]
        ]

        # Crear tabla de información
        info_table = Table(invoice_info, colWidths=[3*inch, 4*inch])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2c3e50')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7'))
        ]))

        elements.append(info_table)
        elements.append(Spacer(1, 20))

        return elements

    def _build_services_table(self, invoice_data: Dict[str, Any]) -> List[Any]:
        """Construir tabla de servicios."""
        elements = []

        # Título de servicios
        services_title = Paragraph("DETALLE DE SERVICIOS", self.styles['CustomSubtitle'])
        elements.append(services_title)

        # Headers de tabla
        headers = [['Descripción', 'Cantidad', 'Valor Unitario', 'Subtotal']]

        # Datos de servicios
        services_data = invoice_data.get('services', [])
        table_data = headers.copy()

        for service in services_data:
            row = [
                service.get('description', ''),
                str(service.get('quantity', 1)),
                f"${service.get('unit_price', 0):,.0f}",
                f"${service.get('subtotal', 0):,.0f}"
            ]
            table_data.append(row)

        # Crear tabla
        services_table = Table(table_data, colWidths=[4*inch, 1*inch, 1.5*inch, 1.5*inch])
        services_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ]))

        elements.append(services_table)
        elements.append(Spacer(1, 20))

        return elements

    def _build_totals(self, invoice_data: Dict[str, Any]) -> List[Any]:
        """Construir sección de totales."""
        elements = []

        # Calcular totales
        subtotal = invoice_data.get('subtotal', 0)
        tax_rate = invoice_data.get('tax_rate', 0.19)  # IVA Colombia
        tax_amount = subtotal * tax_rate
        total = subtotal + tax_amount

        # Tabla de totales
        totals_data = [
            ['Subtotal:', f"${subtotal:,.0f}"],
            [f'IVA ({tax_rate*100:.0f}%):', f"${tax_amount:,.0f}"],
            ['TOTAL:', f"${total:,.0f}"]
        ]

        totals_table = Table(totals_data, colWidths=[5*inch, 2*inch])
        totals_table.setStyle(TableStyle([
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#27ae60')),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7'))
        ]))

        elements.append(totals_table)
        elements.append(Spacer(1, 20))

        return elements

    def _build_terms(self) -> List[Any]:
        """Construir términos y condiciones."""
        elements = []

        terms_title = Paragraph("TÉRMINOS Y CONDICIONES", self.styles['CustomSubtitle'])
        elements.append(terms_title)

        terms_text = """
        <b>1. Condiciones de Pago:</b> El pago debe realizarse en las fechas estipuladas.<br/>
        <b>2. Garantía:</b> Los servicios tienen garantía de 3 meses contra defectos de fabricación.<br/>
        <b>3. Devoluciones:</b> No se aceptan devoluciones de servicios consumidos.<br/>
        <b>4. Jurisdicción:</b> Esta factura se rige por las leyes de Colombia.<br/>
        <b>5. Notas:</b> Gracias por confiar en AndroTech para sus necesidades tecnológicas.
        """

        terms = Paragraph(terms_text, self.styles['Normal'])
        elements.append(terms)
        elements.append(Spacer(1, 30))

        return elements

    def _build_qr_code(self, url: str) -> List[Any]:
        """Construir codigo QR para consulta de reparacion."""
        elements = []
        try:
            qr = QrCodeWidget(url)
            qr.barWidth = 120
            qr.barHeight = 120
            d = Drawing(140, 140)
            d.add(qr)

            # Tabla para centrar QR con texto
            qr_data = [[d], [Paragraph(
                '<para alignment="center"><font size="8" color="#7f8c8d">'
                'Escanea para consultar el estado de tu reparacion'
                '</font></para>',
                self.styles['Normal']
            )]]
            qr_table = Table(qr_data, colWidths=[3*inch])
            qr_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(Spacer(1, 15))
            elements.append(qr_table)
            elements.append(Spacer(1, 15))
        except Exception as e:
            logger.warning(f"No se pudo generar QR: {e}")
        return elements

    def _build_footer(self) -> List[Any]:
        """Construir footer del documento."""
        elements = []

        footer_text = f"""
        <para alignment="center">
        <b>AndroTech</b> - Tu aliado en tecnología móvil<br/>
        Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}<br/>
        Documento electrónico válido sin firma digital
        </para>
        """

        footer = Paragraph(footer_text, self.styles['CompanyInfo'])
        elements.append(footer)

        return elements

    def generate_receipt(self, payment_data: Dict[str, Any], output_path: str) -> bool:
        """
        Generar recibo de pago simple.

        Args:
            payment_data: Datos del pago
            output_path: Ruta donde guardar el PDF

        Returns:
            bool: True si se generó correctamente
        """
        try:
            doc = SimpleDocTemplate(output_path, pagesize=A4)
            elements = []

            # Título
            title = Paragraph("RECIBO DE PAGO", self.styles['CustomTitle'])
            elements.append(title)

            # Información del pago
            receipt_info = [
                ['Fecha:', payment_data.get('date', datetime.now().strftime('%Y-%m-%d'))],
                ['Cliente:', payment_data.get('customer_name', 'N/A')],
                ['Concepto:', payment_data.get('concept', 'Servicio Técnico')],
                ['Monto:', f"${payment_data.get('amount', 0):,.0f} {payment_data.get('currency', 'COP')}"],
                ['Método de Pago:', payment_data.get('payment_method', 'Tarjeta')],
                ['Referencia:', payment_data.get('reference', 'N/A')]
            ]

            receipt_table = Table(receipt_info, colWidths=[2*inch, 4*inch])
            receipt_table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f0f0')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('PADDING', (0, 0), (-1, -1), 8),
            ]))

            elements.append(receipt_table)
            elements.append(Spacer(1, 30))

            # Firma
            signature_text = f"""
            <para alignment="center">
            _______________________________<br/>
            Firma Autorizada<br/>
            AndroTech
            </para>
            """
            signature = Paragraph(signature_text, self.styles['Normal'])
            elements.append(signature)

            doc.build(elements)

            logger.info(f"Payment receipt PDF generated: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to generate receipt PDF: {str(e)}")
            return False

    def generate_quote(self, quote_data: Dict[str, Any], output_path: str) -> bool:
        """
        Generar presupuesto/cotización PDF.

        Args:
            quote_data: Datos del presupuesto
            output_path: Ruta donde guardar el PDF

        Returns:
            bool: True si se generó correctamente
        """
        try:
            # Similar a invoice pero con texto de "presupuesto"
            invoice_data = quote_data.copy()
            invoice_data['document_type'] = 'quote'

            # Crear documento
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=2*cm,
                leftMargin=2*cm,
                topMargin=2*cm,
                bottomMargin=2*cm
            )

            elements = []
            elements.extend(self._build_header())

            # Título de presupuesto
            quote_title = Paragraph("PRESUPUESTO", self.styles['CustomSubtitle'])
            elements.append(quote_title)

            elements.extend(self._build_invoice_info(invoice_data))
            elements.extend(self._build_services_table(invoice_data))
            elements.extend(self._build_totals(invoice_data))

            # Términos para presupuesto
            elements.extend(self._build_quote_terms())

            # QR de consulta
            reparacion_id = invoice_data.get('reparacion_id')
            if reparacion_id:
                consulta_url = f"https://androtech.es/consulta?id={reparacion_id}"
                elements.extend(self._build_qr_code(consulta_url))

            elements.extend(self._build_footer())

            doc.build(elements)

            logger.info(f"Quote PDF generated successfully: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to generate quote PDF: {str(e)}")
            return False

    def _build_quote_terms(self) -> List[Any]:
        """Construir términos para presupuesto."""
        elements = []

        terms_title = Paragraph("TÉRMINOS DEL PRESUPUESTO", self.styles['CustomSubtitle'])
        elements.append(terms_title)

        terms_text = """
        <b>1. Validez:</b> Este presupuesto tiene una validez de 30 días naturales.<br/>
        <b>2. Aprobación:</b> La aceptación del presupuesto implica la conformidad con nuestros términos.<br/>
        <b>3. Precios:</b> Los precios pueden variar según la complejidad final del trabajo.<br/>
        <b>4. Pago:</b> 50% anticipo y 50% contra entrega una vez aprobado el trabajo.<br/>
        <b>5. Garantía:</b> 3 meses de garantía sobre piezas y mano de obra.
        """

        terms = Paragraph(terms_text, self.styles['Normal'])
        elements.append(terms)
        elements.append(Spacer(1, 30))

        return elements


# Instancia global del generador
invoice_generator: Optional[InvoiceGenerator] = None

def init_invoice_generator(template_dir: str = "templates/pdf") -> InvoiceGenerator:
    """Inicializar el generador de facturas global."""
    global invoice_generator
    invoice_generator = InvoiceGenerator(template_dir)
    return invoice_generator

def get_invoice_generator() -> InvoiceGenerator:
    """Obtener la instancia del generador de facturas."""
    if invoice_generator is None:
        raise RuntimeError("Invoice generator not initialized. Call init_invoice_generator() first.")
    return invoice_generator

# Funciones de compatibilidad con código existente
def generar_presupuesto_pdf(reparacion_data, tipo_documento="presupuesto"):
    """
    Función de compatibilidad con código existente.
    Genera un PDF usando la nueva clase InvoiceGenerator.
    """
    if invoice_generator is None:
        init_invoice_generator()

    # Convertir datos antiguos al nuevo formato
    invoice_data = {
        'reparacion_id': reparacion_data.get('id'),
        'invoice_number': f"{'F' if tipo_documento == 'factura' else 'P'}-{reparacion_data.get('id', 'N/A'):05d}",
        'date': datetime.now().strftime('%Y-%m-%d'),
        'customer_name': reparacion_data.get('cliente_nombre', 'N/A'),
        'customer_phone': reparacion_data.get('cliente_telefono', 'N/A'),
        'services': [{
            'description': reparacion_data.get('dispositivo', 'Reparación'),
            'quantity': 1,
            'unit_price': reparacion_data.get('precio', 0),
            'subtotal': reparacion_data.get('precio', 0)
        }],
        'subtotal': reparacion_data.get('precio', 0),
        'tax_rate': 0.19  # IVA Colombia
    }

    # Crear buffer para retorno
    buffer = BytesIO()
    rep_id = reparacion_data.get('id', 'temp')

    if tipo_documento == "factura":
        with tempfile.NamedTemporaryFile(suffix='.pdf', prefix=f'invoice_{rep_id}_', delete=False) as tmp:
            temp_path = tmp.name
        if invoice_generator.generate_invoice(invoice_data, temp_path):
            with open(temp_path, 'rb') as f:
                buffer.write(f.read())
        os.remove(temp_path)
    else:
        with tempfile.NamedTemporaryFile(suffix='.pdf', prefix=f'quote_{rep_id}_', delete=False) as tmp:
            temp_path = tmp.name
        if invoice_generator.generate_quote(invoice_data, temp_path):
            with open(temp_path, 'rb') as f:
                buffer.write(f.read())
        os.remove(temp_path)

    buffer.seek(0)
    return buffer