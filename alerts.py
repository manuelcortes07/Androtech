"""Alert calculation logic used across views and tests.

Keeping this separate makes it easy to test and to reuse from other
modules without importing the whole application.
"""

from datetime import datetime


def calcular_alertas_reparacion(reparacion, ultima_actualizacion=None):
    """Calc alerts/badges dictionary for a given repair.

    Returns a dict with keys ``alertas`` (list of dicts), ``urgencia``
    and ``tiene_alertas``.  The logic mirrors the original implementation
    that lived in :mod:`app`.
    """
    # Convert sqlite3.Row to dict if needed
    if not isinstance(reparacion, dict):
        reparacion = dict(reparacion)
    
    alertas = []
    urgencia = 'normal'

    # 1. Sin presupuesto asignado
    if not reparacion.get('precio') or reparacion.get('precio') <= 0:
        alertas.append({
            'tipo': 'sin_presupuesto',
            'mensaje': 'Sin presupuesto',
            'icono': '💰',
            'color': 'danger'
        })
        urgencia = 'critico'

    # 2. Pago pendiente
    if reparacion.get('precio') and reparacion.get('precio') > 0 and reparacion.get('estado_pago') != 'Pagado':
        alertas.append({
            'tipo': 'pago_pendiente',
            'mensaje': 'Pago pendiente',
            'icono': '⏳',
            'color': 'warning'
        })

    # 3. Reparación atrasada (>7 días sin actualizar)
    if ultima_actualizacion:
        try:
            fecha_act = datetime.strptime(ultima_actualizacion, '%Y-%m-%d %H:%M:%S')
            dias_sin_actualizar = (datetime.now() - fecha_act).days
            if dias_sin_actualizar > 7 and reparacion.get('estado') in ['Pendiente', 'En proceso']:
                alertas.append({
                    'tipo': 'atrasada',
                    'mensaje': f'Atrasada ({dias_sin_actualizar}d)',
                    'icono': '⏰',
                    'color': 'danger'
                })
                if urgencia != 'critico':
                    urgencia = 'importante'
        except Exception:
            pass

    # 4. Terminado pero no entregado
    if reparacion.get('estado') == 'Terminado' and reparacion.get('estado_pago') != 'Pagado':
        alertas.append({
            'tipo': 'pendiente_entrega',
            'mensaje': 'Espera entrega',
            'icono': '📦',
            'color': 'info'
        })

    # Determinar urgencia final
    if any(a['color'] == 'danger' for a in alertas):
        urgencia = 'critico'
    elif any(a['color'] == 'warning' for a in alertas):
        if urgencia != 'critico':
            urgencia = 'advertencia'

    return {
        'alertas': alertas,
        'urgencia': urgencia,
        'tiene_alertas': len(alertas) > 0
    }
