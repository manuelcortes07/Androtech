"""Helpers compartidos de exportación CSV (refactor B1).

Usados por varios dominios (clientes, reparaciones). Se extraen aquí para que los
blueprints los importen sin ciclar con app.py. El emisor del CSV es el TALLER
activo (vía `branding.taller_branding`), nunca una constante.
"""

from __future__ import annotations

from datetime import datetime

from flask import session

from branding import taller_branding

_SEP_CSV = '=' * 62   # separador visual de sección


def _fmt_fecha_csv(fecha_str):
    """Convierte '2026-04-15 20:35:44' o '2026-04-15' a '15/04/2026'."""
    if not fecha_str:
        return ''
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(fecha_str), fmt).strftime('%d/%m/%Y')
        except ValueError:
            continue
    return str(fecha_str)


def _fmt_precio_csv(valor):
    """Formatea un precio como '89,99 €' (coma decimal, sin notacion cientifica)."""
    if valor is None:
        return '0,00 €'
    return f'{float(valor):.2f}'.replace('.', ',') + ' €'


def _csv_filename_prefix():
    """Prefijo de nombre de fichero seguro derivado del nombre del TALLER."""
    base = (taller_branding()['nombre'] or 'Taller')
    base = ''.join(c if c.isalnum() else '_' for c in base).strip('_')
    return base or 'Taller'


def _csv_pie(writer):
    """Pie del CSV con el nombre del TALLER emisor."""
    writer.writerow([f'Fin del informe  |  {taller_branding()["nombre"] or "Taller"}  |  '
                     f'{datetime.now().strftime("%d/%m/%Y %H:%M")}'])


def _csv_empresa_header(writer, titulo):
    """Escribe el bloque de cabecera del CSV con los datos del TALLER emisor."""
    m = taller_branding()
    contacto = '  |  '.join(filter(None, [
        m['direccion'],
        f"Tel: {m['telefono']}" if m['telefono'] else '',
        m['email'],
        f"NIF: {m['nif']}" if m['nif'] else '',
    ]))
    writer.writerow([_SEP_CSV])
    writer.writerow([f'{m["nombre"] or "Taller"} — Taller de Reparación de Dispositivos'])
    if contacto:
        writer.writerow([contacto])
    writer.writerow([_SEP_CSV])
    writer.writerow([])
    writer.writerow([titulo])
    writer.writerow([f'Generado: {datetime.now().strftime("%d/%m/%Y a las %H:%M")}'])
    writer.writerow([f'Exportado por: {session.get("usuario", "sistema")}'])
    writer.writerow([])
