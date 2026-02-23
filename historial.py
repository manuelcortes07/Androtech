"""Helpers for recording repair state changes.

The application stores a history of state transitions in
`reparaciones_historial`; this module exposes a single function that
encapsulates the insert logic and the guard against duplicate entries.
"""

from datetime import datetime
import logging

logger = logging.getLogger("androtech")


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
