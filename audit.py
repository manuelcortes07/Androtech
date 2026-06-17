"""Auditoría y registro de eventos críticos del sistema.

Este módulo proporciona funciones para registrar eventos de auditoría
(logins, cambios de usuarios, reparaciones, pagos) en la tabla audit_log.

Las consultas usan SQLAlchemy a través del modelo `AuditLog` (Fase 1
de la migración SaaS completada; el parámetro `conn` legacy se eliminó
en la limpieza de la Fase 1.9).
"""

import json
import logging
from datetime import datetime

from sqlalchemy import select

from database import Base, get_engine, get_session
from models import AuditLog

logger = logging.getLogger("androtech")


def registrar_auditoria(event_type, usuario, evento_datos, ip_address=None,
                        taller_id=None):
    """Registra un evento de auditoría en la tabla audit_log.

    Args:
        event_type: Tipo de evento (string):
            'login', 'usuario_created', 'usuario_updated', 'usuario_deleted',
            'reparacion_created', 'reparacion_updated', 'reparacion_deleted',
            'pago_registrado', 'cambio_estado'
        usuario: Nombre del usuario que generó el evento
        evento_datos: Dict con información del evento (se serializa a JSON)
        ip_address: Dirección IP del cliente (opcional)
        taller_id: taller al que pertenece el evento (opcional). Si se omite, el
            auto-stamp (`before_flush`) lo fija a `g.taller_id` cuando hay
            request con scope. Se pasa EXPLÍCITO en eventos de PLATAFORMA fuera
            de un request con taller (p. ej. webhook de suscripción del SaaS,
            Fase 3b), donde `g.taller_id` no aplica.

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
            # taller_id explícito gana al auto-stamp (before_flush sólo rellena
            # cuando es None). Así el evento de plataforma queda con su taller.
            s.add(AuditLog(
                taller_id=taller_id,
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


def obtener_auditoria_reciente(limite=20, event_type=None):
    """Obtiene los eventos de auditoría más recientes.

    Args:
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


def crear_tabla_auditoria():
    """Crea la tabla audit_log si no existe.

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
