"""Helpers for recording repair state changes.

The application stores a history of state transitions in
`reparaciones_historial`; this module exposes a single function that
encapsulates the insert logic and the guard against duplicate entries.

Las dos consultas de `registrar_cambio_estado` usan SQLAlchemy con los
modelos ORM `Reparacion` y `RepairHistorial` (el `text()` provisional
de la Fase 1.2 se sustituyó en la limpieza de la Fase 1.9, cuando el
modelo `Reparacion` ya existía).

`validar_transicion` es lógica pura sin acceso a BD.
"""

from datetime import datetime
import logging

from sqlalchemy import select

from database import get_session
from models import Reparacion, RepairHistorial

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


def registrar_cambio_estado(reparacion_id, estado_nuevo, usuario=None):
    """Record a state change if the new value differs from the previous one.

    Args:
        reparacion_id: ID de la reparación cuyo estado cambia.
        estado_nuevo: Estado destino.
        usuario: Nombre del usuario que provoca el cambio (opcional).

    Returns:
        bool: True si se insertó una fila en `reparaciones_historial`,
              False si la reparación no existe o el estado no cambia
              realmente (no-op deseado para evitar ruido).

    Contrato con los llamadores: esta función lee el estado VIGENTE en BD
    en su propia sesión, así que debe invocarse ANTES de commitear el
    update del nuevo estado (como hace editar_reparacion en app.py).
    """
    try:
        with get_session() as s:
            estado_anterior = s.scalars(
                select(Reparacion.estado).where(Reparacion.id == reparacion_id)
            ).first()

            if estado_anterior is None:
                return False
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
