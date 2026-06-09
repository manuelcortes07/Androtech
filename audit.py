"""Auditoría y registro de eventos críticos del sistema.

Este módulo proporciona funciones para registrar eventos de auditoría
(logins, cambios de usuarios, reparaciones, pagos) en la tabla audit_log.

Fase 1.1 de la migración SaaS: las consultas usan SQLAlchemy a través
del modelo `AuditLog`. El parámetro `conn` (sqlite3.Connection) que
recibían las funciones se mantiene por compatibilidad con los llamadores
de `app.py` pero se ignora — internamente abrimos `Session` propia.
"""

from datetime import datetime
import logging
import json

from sqlalchemy import select

from database import get_engine, get_session, Base
from models import AuditLog

logger = logging.getLogger("androtech")


def registrar_auditoria(conn, event_type, usuario, evento_datos, ip_address=None):
    """Registra un evento de auditoría en la tabla audit_log.

    Args:
        conn: parámetro legacy (sqlite3.Connection). **Ignorado**; se mantiene
              por compatibilidad con los ~30 puntos de llamada en app.py.
        event_type: Tipo de evento (string):
            'login', 'usuario_created', 'usuario_updated', 'usuario_deleted',
            'reparacion_created', 'reparacion_updated', 'reparacion_deleted',
            'pago_registrado', 'cambio_estado'
        usuario: Nombre del usuario que generó el evento
        evento_datos: Dict con información del evento (se serializa a JSON)
        ip_address: Dirección IP del cliente (opcional)

    Returns:
        bool: True si se registró exitosamente, False en caso de error
    """
    try:
        # Serialización idéntica al comportamiento previo
        if isinstance(evento_datos, dict):
            evento_json = json.dumps(evento_datos, ensure_ascii=False)
        else:
            evento_json = str(evento_datos)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with get_session() as s:
            s.add(AuditLog(
                event_type=event_type,
                usuario=usuario,
                evento_datos=evento_json,
                ip_address=ip_address,
                timestamp=timestamp,
            ))
            s.commit()

        return True

    except Exception as e:
        logger.error(f"Error registrando auditoría: {e}")
        return False


def obtener_auditoria_reciente(conn=None, limite=20, event_type=None):
    """Obtiene los eventos de auditoría más recientes.

    Args:
        conn: parámetro legacy. **Ignorado**; se mantiene por compatibilidad.
        limite: Número máximo de registros a retornar (default 20)
        event_type: Filtrar por tipo de evento (default: todos)

    Returns:
        list: Lista de dicts con las columnas del audit_log, ordenados por
              timestamp descendente. Formato idéntico al previo (listas de
              dicts vía sqlite3.Row) para que el llamador (`/admin/auditoria`)
              no necesite cambios.
    """
    try:
        with get_session() as s:
            if event_type:
                stmt = (
                    select(AuditLog)
                    .where(AuditLog.event_type == event_type)
                    .order_by(AuditLog.timestamp.desc())
                    .limit(limite)
                )
            else:
                stmt = (
                    select(AuditLog)
                    .order_by(AuditLog.timestamp.desc())
                    .limit(limite)
                )
            rows = s.scalars(stmt).all()
            return [
                {
                    "id": r.id,
                    "event_type": r.event_type,
                    "usuario": r.usuario,
                    "evento_datos": r.evento_datos,
                    "ip_address": r.ip_address,
                    "timestamp": r.timestamp,
                }
                for r in rows
            ]

    except Exception as e:
        logger.error(f"Error obteniendo auditoría: {e}")
        return []


def crear_tabla_auditoria(conn=None):
    """Crea la tabla audit_log si no existe.

    Args:
        conn: parámetro legacy. **Ignorado**; se mantiene por compatibilidad.

    Returns:
        bool: True si se creó o ya existe, False en caso de error.
    """
    try:
        Base.metadata.create_all(get_engine(), tables=[AuditLog.__table__])
        logger.info("Tabla audit_log creada/verificada")
        return True

    except Exception as e:
        logger.error(f"Error creando tabla audit_log: {e}")
        return False
