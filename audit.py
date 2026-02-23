"""Auditoría y registro de eventos críticos del sistema.

Este módulo proporciona funciones para registrar eventos de auditoría
(logins, cambios de usuarios, reparaciones, pagos) en la tabla audit_log.
Los registros se utilizan para hacer seguimiento y cumplimiento normativo.
"""

from datetime import datetime
import logging
import json

logger = logging.getLogger("androtech")


def registrar_auditoria(conn, event_type, usuario, evento_datos, ip_address=None):
    """Registra un evento de auditoría en la tabla audit_log.
    
    Args:
        conn: SQLite connection object
        event_type: Tipo de evento (string): 
            'login', 'usuario_created', 'usuario_updated', 'usuario_deleted',
            'reparacion_created', 'reparacion_updated', 'reparacion_deleted',
            'pago_registrado', 'cambio_estado'
        usuario: Nombre del usuario que generó el evento
        evento_datos: Dict con información del evento
        ip_address: Dirección IP del cliente (opcional)
    
    Returns:
        bool: True si se registró exitosamente, False en caso de error
    """
    try:
        # Convertir evento_datos a JSON
        if isinstance(evento_datos, dict):
            evento_json = json.dumps(evento_datos, ensure_ascii=False)
        else:
            evento_json = str(evento_datos)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn.execute("""
            INSERT INTO audit_log (event_type, usuario, evento_datos, ip_address, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (event_type, usuario, evento_json, ip_address, timestamp))
        
        conn.commit()
        return True
    
    except Exception as e:
        logger.error(f"Error registrando auditoría: {e}")
        return False


def obtener_auditoria_reciente(conn, limite=20, event_type=None):
    """Obtiene los eventos de auditoría más recientes.
    
    Args:
        conn: SQLite connection object
        limite: Número máximo de registros a retornar (default 20)
        event_type: Filtrar por tipo de evento (default: todos)
    
    Returns:
        list: Lista de eventos ordenados por timestamp descendente
    """
    try:
        if event_type:
            query = """
                SELECT * FROM audit_log
                WHERE event_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """
            registros = conn.execute(query, (event_type, limite)).fetchall()
        else:
            query = """
                SELECT * FROM audit_log
                ORDER BY timestamp DESC
                LIMIT ?
            """
            registros = conn.execute(query, (limite,)).fetchall()
        
        return [dict(r) for r in registros] if registros else []
    
    except Exception as e:
        logger.error(f"Error obteniendo auditoría: {e}")
        return []


def crear_tabla_auditoria(conn):
    """Crea la tabla audit_log si no existe.
    
    Args:
        conn: SQLite connection object
    
    Returns:
        bool: True si se creó o ya existe, False en caso de error
    """
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                usuario TEXT,
                evento_datos TEXT,
                ip_address TEXT,
                timestamp TEXT NOT NULL,
                UNIQUE(event_type, usuario, timestamp)
            )
        """)
        
        # Crear índice para búsquedas frecuentes
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
            ON audit_log(timestamp DESC)
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_event_type 
            ON audit_log(event_type)
        """)
        
        conn.commit()
        logger.info("Tabla audit_log creada/verificada")
        return True
    
    except Exception as e:
        logger.error(f"Error creando tabla audit_log: {e}")
        return False
