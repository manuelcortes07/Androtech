"""Modelos ORM — Fase 1.1 (auth + audit).

Reflejan EXACTAMENTE el esquema SQLite actual. Cero cambios de esquema.
Las columnas, defaults, NOT NULL y constraints coinciden con lo que
extraje vía `PRAGMA table_info` en el informe de auditoría.

Cuando se añadan más modelos en futuras fases (clientes, reparaciones,
inventario, etc.), van aquí. Cuando llegue Fase 2 multi-tenant, se
añadirá la columna `taller_id` en este fichero y se generará la
migración correspondiente.

Detalle Python sutil: la columna `usuarios.contraseña` lleva ñ en SQL.
Para no obligar a escribir `user.contraseña` en código Python (válido
pero feo), exponemos el atributo Python como `password` y mapeamos al
nombre SQL real `contraseña` con el primer argumento de `Column()`.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)

from database import Base


class Usuario(Base):
    """Cuentas de técnicos y administradores del taller.

    Tabla: `usuarios`. La columna SQL `contraseña` (con ñ) se expone aquí
    como atributo Python `password` para mayor comodidad.
    """

    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario = Column(Text, nullable=False, unique=True)
    password = Column("contraseña", Text, nullable=False)
    rol = Column(Text, default="tecnico")

    def __repr__(self) -> str:
        return f"<Usuario(id={self.id}, usuario={self.usuario!r}, rol={self.rol!r})>"


class Rol(Base):
    """Catálogo de roles del sistema (admin, tecnico).

    Decisión de producto (CLAUDE.md): roles GLOBALES, NO por taller.
    Esta tabla NO recibirá `taller_id` en Fase 2.
    """

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(Text, nullable=False, unique=True)
    descripcion = Column(Text)
    es_sistema = Column(Integer, default=0)
    color = Column(Text, default="#6c757d")

    def __repr__(self) -> str:
        return f"<Rol(id={self.id}, nombre={self.nombre!r})>"


class PermisoRol(Base):
    """Mapping rol → permiso.

    Misma decisión: GLOBAL, sin `taller_id`. UNIQUE composite garantiza
    que un rol no acumule duplicados del mismo permiso.
    """

    __tablename__ = "permisos_rol"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rol_nombre = Column(Text, nullable=False)
    permiso = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("rol_nombre", "permiso", name="uq_permisos_rol"),
    )

    def __repr__(self) -> str:
        return f"<PermisoRol(rol={self.rol_nombre!r}, permiso={self.permiso!r})>"


class AuditLog(Base):
    """Eventos críticos del sistema (login, pagos, cambios de usuarios…).

    En Fase 2 esta tabla recibirá `taller_id` NULLABLE: los eventos del
    superadmin de plataforma viajarán con `NULL` y los del taller con
    su `taller_id` correspondiente.
    """

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(Text, nullable=False)
    usuario = Column(Text)
    evento_datos = Column(Text)  # JSON serializado a string
    ip_address = Column(Text)
    timestamp = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "event_type", "usuario", "timestamp", name="uq_audit_event"
        ),
        Index("idx_audit_event_type", "event_type"),
        Index("idx_audit_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, event_type={self.event_type!r}, "
            f"usuario={self.usuario!r}, timestamp={self.timestamp!r})>"
        )
