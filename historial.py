"""Helpers for recording repair state changes.

The application stores a history of state transitions in
`reparaciones_historial`; this module exposes a single function that
encapsulates the insert logic and the guard against duplicate entries.
"""

from datetime import datetime
import logging

logger = logging.getLogger("androtech")

# Estados válidos y transiciones permitidas para técnicos
ESTADOS_VALIDOS = ('Pendiente', 'En proceso', 'Terminado', 'Entregado')

TRANSICIONES_VALIDAS = {
    'Pendiente': ('En proceso',),
    'En proceso': ('Pendiente', 'Terminado'),
    'Terminado': ('En proceso', 'Entregado'),
    'Entregado': (),
}


def validar_transicion(estado_actual, estado_nuevo, rol='tecnico'):
    """Valida si una transición de estado es permitida.

    Los administradores pueden realizar cualquier transición entre
    estados válidos.  Los técnicos solo pueden seguir las transiciones
    definidas en ``TRANSICIONES_VALIDAS``.

    Returns (bool, str): (es_valida, mensaje_error)
    """
    if estado_nuevo not in ESTADOS_VALIDOS:
        return False, f'Estado "{estado_nuevo}" no es válido'

    if estado_actual == estado_nuevo:
        return True, ''

    if rol == 'admin':
        return True, ''

    permitidos = TRANSICIONES_VALIDAS.get(estado_actual, ())
    if estado_nuevo not in permitidos:
        return False, f'No se puede cambiar de "{estado_actual}" a "{estado_nuevo}"'

    return True, ''


def registrar_cambio_estado(conn, reparacion_id, estado_nuevo, usuario=None):
    """Record a state change if the new value differs from the previous one.

    Parameters mirror those used in the original implementation. The
    connection object is expected to be an SQLite3 connection.

    Returns ``True`` if a row was added, ``False`` otherwise (e.g. because
    the state did not actually change or the repair ID did not exist).
    """
    try:
        reparacion = conn.execute(
            "SELECT estado FROM reparaciones WHERE id=?", 
            (reparacion_id,)
        ).fetchone()
        if not reparacion:
            return False

        estado_anterior = reparacion['estado']
        if estado_anterior == estado_nuevo:
            return False

        fecha_cambio = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO reparaciones_historial 
            (reparacion_id, estado_anterior, estado_nuevo, fecha_cambio, usuario)
            VALUES (?, ?, ?, ?, ?)
        """, (reparacion_id, estado_anterior, estado_nuevo, fecha_cambio, usuario))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error registrando cambio de estado: {e}")
        return False
