"""Modelos ORM de AndroTech.

Multi-tenant (Fase 2): las 9 tablas de scope llevan `taller_id NOT NULL`
con `server_default="1"` (los datos existentes son el taller 1; los inserts
que no fijan taller_id lo reciben de la BD). `audit_log` lo lleva nullable
(eventos de plataforma → NULL). `roles` y `permisos_rol` NO lo llevan
(decisión de producto: roles globales del sistema).

El `taller_id` se asigna automáticamente al taller activo en la Fase 2.3
(event listener `before_flush`) y se FILTRA automáticamente vía
`with_loader_criteria` — ver `database.py`.

Detalle Python sutil: la columna `usuarios.contraseña` lleva ñ en SQL.
Para no obligar a escribir `user.contraseña` en código Python (válido
pero feo), exponemos el atributo Python como `password` y mapeamos al
nombre SQL real `contraseña` con el primer argumento de `Column()`.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)

from database import Base


class Taller(Base):
    """El tenant: un taller de reparación que usa la plataforma.

    Todo lo demás (usuarios, clientes, reparaciones, inventario, …) cuelga
    de aquí vía `taller_id`. El `slug` (UNIQUE) aparece en las URLs
    `/t/{slug}/...` (decisión de producto: identificación por path).
    """

    __tablename__ = "talleres"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(Text, nullable=False)
    slug = Column(Text, nullable=False, unique=True)
    email_contacto = Column(Text)
    telefono = Column(Text)
    direccion = Column(Text)
    fecha_alta = Column(Text, nullable=False)
    estado = Column(Text, nullable=False, default="activo",
                    server_default=text("'activo'"))   # trial|activo|suspendido|cancelado
    plan = Column(Text, nullable=False, default="basico",
                  server_default=text("'basico'"))
    stripe_customer_id = Column(Text)
    stripe_sub_id = Column(Text)
    fecha_fin_periodo = Column(Text)
    config = Column(Text)  # JSON serializado: iva_rate, moneda, logo_url, branding…

    def __repr__(self) -> str:
        return f"<Taller(id={self.id}, slug={self.slug!r}, estado={self.estado!r})>"


class Usuario(Base):
    """Cuentas de técnicos y administradores del taller.

    Tabla: `usuarios`. La columna SQL `contraseña` (con ñ) se expone aquí
    como atributo Python `password` para mayor comodidad.
    """

    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    taller_id = Column(Integer, ForeignKey("talleres.id"), nullable=False,
                       server_default="1")
    # El UNIQUE pasa de (usuario) a (taller_id, usuario): cada taller puede
    # tener su propio "admin".
    usuario = Column(Text, nullable=False)
    password = Column("contraseña", Text, nullable=False)
    rol = Column(Text, default="tecnico", server_default=text("'tecnico'"))

    __table_args__ = (
        UniqueConstraint("taller_id", "usuario", name="uq_usuarios_taller_usuario"),
    )

    def __repr__(self) -> str:
        return (f"<Usuario(id={self.id}, taller_id={self.taller_id}, "
                f"usuario={self.usuario!r}, rol={self.rol!r})>")


class Rol(Base):
    """Catálogo de roles del sistema (admin, tecnico).

    Decisión de producto (CLAUDE.md): roles GLOBALES, NO por taller.
    Esta tabla NO recibirá `taller_id` en Fase 2.
    """

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(Text, nullable=False, unique=True)
    descripcion = Column(Text)
    es_sistema = Column(Integer, default=0, server_default=text("0"))
    color = Column(Text, default="#6c757d", server_default=text("'#6c757d'"))

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
    # NULLABLE a propósito: eventos del superadmin de plataforma llevan NULL;
    # los eventos de un taller llevan su taller_id.
    taller_id = Column(Integer, ForeignKey("talleres.id"), nullable=True)
    event_type = Column(Text, nullable=False)
    usuario = Column(Text)
    evento_datos = Column(Text)  # JSON serializado a string
    ip_address = Column(Text)
    timestamp = Column(Text, nullable=False)

    __table_args__ = (
        # taller_id va en el UNIQUE: per-taller dedup. Sin él, el "admin" de
        # dos talleres logueándose en el mismo segundo colisionaría y se
        # perdería un evento de auditoría (Fase 2.2).
        UniqueConstraint(
            "taller_id", "event_type", "usuario", "timestamp",
            name="uq_audit_event"
        ),
        Index("idx_audit_event_type", "event_type"),
        Index("idx_audit_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, event_type={self.event_type!r}, "
            f"usuario={self.usuario!r}, timestamp={self.timestamp!r})>"
        )


class Cliente(Base):
    """Clientes finales del taller.

    Tabla `clientes` — el modelo más simple del dominio: 5 columnas, sin
    FKs salientes. En Fase 2 recibirá `taller_id` NOT NULL.
    """

    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    taller_id = Column(Integer, ForeignKey("talleres.id"), nullable=False,
                       server_default="1")
    nombre = Column(Text, nullable=False)
    telefono = Column(Text)
    email = Column(Text)
    direccion = Column(Text)

    def __repr__(self) -> str:
        return f"<Cliente(id={self.id}, nombre={self.nombre!r})>"


class Reparacion(Base):
    """Documento central del negocio: una reparación de un dispositivo.

    Tabla `reparaciones` — 13 columnas. La firma digital vive en la columna
    `firma` (base64/filename), NO en una tabla aparte. En Fase 2 recibirá
    `taller_id` NOT NULL y la FK compuesta con clientes del mismo taller.
    """

    __tablename__ = "reparaciones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    taller_id = Column(Integer, ForeignKey("talleres.id"), nullable=False,
                       server_default="1")
    cliente_id = Column(Integer, ForeignKey("clientes.id"))
    dispositivo = Column(Text, nullable=False)
    descripcion = Column(Text)
    estado = Column(Text, default="Pendiente", server_default=text("'Pendiente'"))
    fecha_entrada = Column(Text)
    fecha_salida = Column(Text)
    precio = Column(Float)
    tipo_documento = Column(Text, default="presupuesto",
                            server_default=text("'presupuesto'"))
    estado_pago = Column(Text, default="Pendiente",
                         server_default=text("'Pendiente'"))
    fecha_pago = Column(Text)
    metodo_pago = Column(Text)
    firma = Column(Text)

    def __repr__(self) -> str:
        return (f"<Reparacion(id={self.id}, dispositivo={self.dispositivo!r}, "
                f"estado={self.estado!r})>")


class FotoReparacion(Base):
    """Imágenes subidas (drag&drop) asociadas a una reparación."""

    __tablename__ = "fotos_reparacion"

    id = Column(Integer, primary_key=True, autoincrement=True)
    taller_id = Column(Integer, ForeignKey("talleres.id"), nullable=False,
                       server_default="1")
    # ON DELETE CASCADE: igual que el DDL SQLite original (en Postgres SÍ se
    # aplica; en SQLite es cosmético porque las FKs están OFF).
    reparacion_id = Column(Integer, ForeignKey("reparaciones.id", ondelete="CASCADE"),
                           nullable=False)
    filename = Column(Text, nullable=False)
    descripcion = Column(Text)
    fecha_subida = Column(Text, nullable=False)
    subido_por = Column(Text)

    def __repr__(self) -> str:
        return f"<FotoReparacion(id={self.id}, reparacion_id={self.reparacion_id})>"


class NotaReparacion(Base):
    """Notas internas de los técnicos sobre una reparación."""

    __tablename__ = "notas_reparacion"

    id = Column(Integer, primary_key=True, autoincrement=True)
    taller_id = Column(Integer, ForeignKey("talleres.id"), nullable=False,
                       server_default="1")
    # ON DELETE CASCADE: igual que el DDL SQLite original.
    reparacion_id = Column(Integer, ForeignKey("reparaciones.id", ondelete="CASCADE"),
                           nullable=False)
    usuario = Column(Text, nullable=False)
    contenido = Column(Text, nullable=False)
    fecha_creacion = Column(Text, nullable=False)
    es_importante = Column(Integer, default=0, server_default=text("0"))

    def __repr__(self) -> str:
        return f"<NotaReparacion(id={self.id}, reparacion_id={self.reparacion_id})>"


class InventarioPieza(Base):
    """Stock de piezas del taller.

    El modelo se declara en Fase 1.5 (lo necesita la FK de PiezaReparacion)
    pero sus handlers (/inventario/*) se migran en Fase 1.6.
    """

    __tablename__ = "inventario_piezas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    taller_id = Column(Integer, ForeignKey("talleres.id"), nullable=False,
                       server_default="1")
    nombre = Column(Text, nullable=False)
    categoria = Column(Text, default="General", server_default=text("'General'"))
    descripcion = Column(Text)
    cantidad = Column(Integer, default=0, server_default=text("0"))
    cantidad_minima = Column(Integer, default=5, server_default=text("5"))
    precio_coste = Column(Float, default=0, server_default=text("0"))
    precio_venta = Column(Float, default=0, server_default=text("0"))
    proveedor = Column(Text)
    ubicacion = Column(Text)
    fecha_actualizacion = Column(Text)

    def __repr__(self) -> str:
        return f"<InventarioPieza(id={self.id}, nombre={self.nombre!r}, cantidad={self.cantidad})>"


class PiezaReparacion(Base):
    """Piezas del inventario consumidas en una reparación concreta."""

    __tablename__ = "piezas_reparacion"

    id = Column(Integer, primary_key=True, autoincrement=True)
    taller_id = Column(Integer, ForeignKey("talleres.id"), nullable=False,
                       server_default="1")
    reparacion_id = Column(Integer, ForeignKey("reparaciones.id"), nullable=False)
    pieza_id = Column(Integer, ForeignKey("inventario_piezas.id"), nullable=False)
    cantidad = Column(Integer, default=1, server_default=text("1"))
    fecha_uso = Column(Text, nullable=False)
    usuario = Column(Text)

    def __repr__(self) -> str:
        return (f"<PiezaReparacion(id={self.id}, reparacion_id={self.reparacion_id}, "
                f"pieza_id={self.pieza_id})>")


class SolicitudReparacion(Base):
    """Solicitudes de reparación enviadas desde el portal público.

    En Fase 2 recibirá `taller_id` NOT NULL — la solicitud debe llegar al
    taller cuyo slug aparece en la URL pública (/t/{slug}/solicitar-reparacion).
    """

    __tablename__ = "solicitudes_reparacion"

    id = Column(Integer, primary_key=True, autoincrement=True)
    taller_id = Column(Integer, ForeignKey("talleres.id"), nullable=False,
                       server_default="1")
    nombre = Column(Text, nullable=False)
    telefono = Column(Text, nullable=False)
    email = Column(Text)
    dispositivo = Column(Text, nullable=False)
    marca = Column(Text)
    modelo = Column(Text)
    descripcion = Column(Text, nullable=False)
    urgencia = Column(Text, default="normal", server_default=text("'normal'"))
    fecha_preferida = Column(Text)
    horario_preferido = Column(Text)
    estado = Column(Text, default="pendiente", server_default=text("'pendiente'"))
    notas_admin = Column(Text)
    fecha_solicitud = Column(Text, nullable=False)
    fecha_gestion = Column(Text)

    def __repr__(self) -> str:
        return (f"<SolicitudReparacion(id={self.id}, nombre={self.nombre!r}, "
                f"estado={self.estado!r})>")


class RepairHistorial(Base):
    """Trazabilidad de cambios de estado de una reparación.

    Cada fila representa una transición de estado: estado_anterior → estado_nuevo,
    con timestamp y usuario responsable. Insertada por
    `historial.registrar_cambio_estado()` solo cuando el estado cambia
    realmente — nunca se inserta para "actualizaciones" que dejan el estado
    igual.

    Fase 2 multi-tenant: esta tabla recibirá `taller_id` desnormalizado para
    evitar JOIN con `reparaciones` en cada consulta del filtro automático.

    FK restaurada en Fase 1.5: en la Fase 1.2 se quitó temporalmente
    porque el modelo `Reparacion` no existía y SQLAlchemy fallaba al
    resolverla en el flush. Ahora `Reparacion` está declarado arriba y
    la FK vuelve a su sitio.
    """

    __tablename__ = "reparaciones_historial"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Desnormalizado: hereda el taller vía reparacion_id pero lleva taller_id
    # propio para que el filtro automático no tenga que hacer JOIN.
    taller_id = Column(Integer, ForeignKey("talleres.id"), nullable=False,
                       server_default="1")
    reparacion_id = Column(Integer, ForeignKey("reparaciones.id"), nullable=False)
    estado_anterior = Column(Text)
    estado_nuevo = Column(Text, nullable=False)
    fecha_cambio = Column(Text, nullable=False)
    usuario = Column(Text)

    __table_args__ = (
        Index("idx_historial_reparacion", "reparacion_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<RepairHistorial(id={self.id}, reparacion_id={self.reparacion_id}, "
            f"{self.estado_anterior!r}->{self.estado_nuevo!r})>"
        )
