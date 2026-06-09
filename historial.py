"""Helpers for recording repair state changes.

The application stores a history of state transitions in
`reparaciones_historial`; this module exposes a single function that
encapsulates the insert logic and the guard against duplicate entries.

Fase 1.2 de la migración SaaS: las dos consultas de
`registrar_cambio_estado` usan SQLAlchemy. La inserción en
`reparaciones_historial` va por el modelo ORM `RepairHistorial`; la
lectura de `reparaciones.estado` usa SQL crudo vía `text()` porque el
modelo `Reparacion` aún no existe — se migrará en una fase posterior.

Cuando se cree el modelo `Reparacion`, sustituir la sentencia `text()`
por `select(Reparacion.estado).where(Reparacion.id == reparacion_id)`.

`validar_transicion` es lógica pura sin acceso a BD: no se toca.
"""

from datetime import datetime
import logging

from sqlalchemy import text

from database import get_session
from models import RepairHistorial

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

    Args:
        conn: parámetro legacy (sqlite3.Connection). **Ignorado**; se mantiene
              por compatibilidad con los llamadores en app.py. Internamente
              se abre una `Session` SQLAlchemy.
        reparacion_id: ID de la reparación cuyo estado cambia.
        estado_nuevo: Estado destino.
        usuario: Nombre del usuario que provoca el cambio (opcional).

    Returns:
        bool: True si se insertó una fila en `reparaciones_historial`,
              False si la reparación no existe o el estado no cambia
              realmente (no-op deseado para evitar ruido).
    """
    try:
        with get_session() as s:
            # Lectura del estado actual. Modelo `Reparacion` aún no existe
            # (vendrá en una fase posterior), así que usamos `text()` para
            # mantener el SQL crudo de forma idiomática.
            row = s.execute(
                text("SELECT estado FROM reparaciones WHERE id = :id"),
                {"id": reparacion_id},
            ).first()

            if not row:
                return False

            estado_anterior = row[0]
            if estado_anterior == estado_nuevo:
                return False

            fecha_cambio = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            s.add(RepairHistorial(
                reparacion_id=reparacion_id,
                estado_anterior=estado_anterior,
                estado_nuevo=estado_nuevo,
                fecha_cambio=fecha_cambio,
                usuario=usuario,
            ))
            s.commit()
            return True

    except Exception as e:
        logger.error(f"Error registrando cambio de estado: {e}")
        return False
