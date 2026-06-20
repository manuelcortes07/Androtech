"""Authentication, authorization and permissions.

This module contains decorators for login, role enforcement and
granular permission checks. It also defines the default permissions
for the built-in roles ('admin' and 'tecnico').

Fase 1.1 de la migración SaaS: las consultas a BD usan SQLAlchemy
(módulos `database` y `models`). El parámetro `conn` que `app.py` sigue
pasando a `init_permisos_db()` se mantiene por compatibilidad pero se
ignora internamente — cada función abre su propia `Session`.
"""

from functools import wraps

from flask import abort, flash, redirect, session, url_for
from sqlalchemy import select

from database import Base, get_engine, get_session, insert_or_ignore
from models import PermisoRol, Rol

# ─── Definicion de permisos disponibles ──────────────────────────────
# Cada permiso tiene: clave interna, nombre visible, categoria
PERMISOS_DISPONIBLES = [
    # Clientes
    {'clave': 'clientes_ver',       'nombre': 'Ver clientes',            'categoria': 'Clientes'},
    {'clave': 'clientes_crear',     'nombre': 'Crear clientes',          'categoria': 'Clientes'},
    {'clave': 'clientes_editar',    'nombre': 'Editar clientes',         'categoria': 'Clientes'},
    {'clave': 'clientes_borrar',    'nombre': 'Borrar clientes',         'categoria': 'Clientes'},
    {'clave': 'clientes_historial', 'nombre': 'Ver historial cliente',   'categoria': 'Clientes'},
    {'clave': 'clientes_exportar',  'nombre': 'Exportar clientes CSV',   'categoria': 'Clientes'},

    # Reparaciones
    {'clave': 'reparaciones_ver',       'nombre': 'Ver reparaciones',         'categoria': 'Reparaciones'},
    {'clave': 'reparaciones_crear',     'nombre': 'Crear reparaciones',       'categoria': 'Reparaciones'},
    {'clave': 'reparaciones_editar',    'nombre': 'Editar reparaciones',      'categoria': 'Reparaciones'},
    {'clave': 'reparaciones_borrar',    'nombre': 'Borrar reparaciones',      'categoria': 'Reparaciones'},
    {'clave': 'reparaciones_exportar',  'nombre': 'Exportar reparaciones CSV','categoria': 'Reparaciones'},
    {'clave': 'reparaciones_pdf',       'nombre': 'Generar PDFs',             'categoria': 'Reparaciones'},
    {'clave': 'reparaciones_fotos',     'nombre': 'Gestionar fotos',          'categoria': 'Reparaciones'},
    {'clave': 'reparaciones_notas',     'nombre': 'Gestionar notas',          'categoria': 'Reparaciones'},
    {'clave': 'reparaciones_firma',     'nombre': 'Gestionar firma digital',  'categoria': 'Reparaciones'},
    {'clave': 'reparaciones_pago',      'nombre': 'Marcar como pagado',       'categoria': 'Reparaciones'},
    {'clave': 'reparaciones_ticket',    'nombre': 'Generar ticket QR',        'categoria': 'Reparaciones'},

    # Inventario
    {'clave': 'inventario_ver',     'nombre': 'Ver inventario',     'categoria': 'Inventario'},
    {'clave': 'inventario_crear',   'nombre': 'Crear piezas',       'categoria': 'Inventario'},
    {'clave': 'inventario_editar',  'nombre': 'Editar piezas',      'categoria': 'Inventario'},
    {'clave': 'inventario_borrar',  'nombre': 'Borrar piezas',      'categoria': 'Inventario'},
    {'clave': 'inventario_usar',    'nombre': 'Usar piezas en reparaciones', 'categoria': 'Inventario'},

    # Calendario y Dashboard
    {'clave': 'dashboard_ver',      'nombre': 'Ver dashboard',      'categoria': 'General'},
    {'clave': 'calendario_ver',     'nombre': 'Ver calendario',     'categoria': 'General'},
    {'clave': 'busqueda_global',    'nombre': 'Busqueda global',    'categoria': 'General'},

    # Administracion
    {'clave': 'usuarios_ver',       'nombre': 'Ver usuarios',         'categoria': 'Administracion'},
    {'clave': 'usuarios_crear',     'nombre': 'Crear usuarios',       'categoria': 'Administracion'},
    {'clave': 'usuarios_editar',    'nombre': 'Editar usuarios',      'categoria': 'Administracion'},
    {'clave': 'usuarios_borrar',    'nombre': 'Borrar usuarios',      'categoria': 'Administracion'},
    {'clave': 'roles_gestionar',    'nombre': 'Gestionar roles y permisos', 'categoria': 'Administracion'},
    {'clave': 'solicitudes_ver',    'nombre': 'Ver solicitudes de reparacion', 'categoria': 'Administracion'},
]

# Permisos por defecto para cada rol base
PERMISOS_ADMIN = [p['clave'] for p in PERMISOS_DISPONIBLES]  # Todos

PERMISOS_TECNICO = [
    'clientes_ver', 'clientes_crear', 'clientes_editar', 'clientes_historial',
    'reparaciones_ver', 'reparaciones_crear', 'reparaciones_editar',
    'reparaciones_pdf', 'reparaciones_fotos', 'reparaciones_notas',
    'reparaciones_firma', 'reparaciones_pago', 'reparaciones_ticket',
    'inventario_usar',
    'dashboard_ver', 'calendario_ver', 'busqueda_global',
]


def init_permisos_db():
    """Create permissions tables and seed default roles (SQLAlchemy)."""
    engine = get_engine()

    # Crear las tablas si no existen. SQLAlchemy genera el DDL equivalente
    # al CREATE TABLE IF NOT EXISTS original.
    Base.metadata.create_all(
        engine, tables=[Rol.__table__, PermisoRol.__table__]
    )

    with get_session() as s:
        existing_names = set(s.scalars(select(Rol.nombre)).all())

        if 'admin' not in existing_names:
            s.add(Rol(
                nombre='admin',
                descripcion='Acceso completo al sistema. No se puede eliminar.',
                es_sistema=1,
                color='#dc3545',
            ))
            # Equivalente a INSERT OR IGNORE: con la dialect-specific de SQLite
            # mantenemos la semántica original (no romper si algún permiso ya
            # existiera por alguna razón).
            for p in PERMISOS_ADMIN:
                stmt = (
                    insert_or_ignore(PermisoRol)
                    .values(rol_nombre='admin', permiso=p)
                    .on_conflict_do_nothing()
                )
                s.execute(stmt)

        if 'tecnico' not in existing_names:
            s.add(Rol(
                nombre='tecnico',
                descripcion='Acceso a reparaciones, clientes y herramientas basicas.',
                es_sistema=1,
                color='#2B8AC4',
            ))
            for p in PERMISOS_TECNICO:
                stmt = (
                    insert_or_ignore(PermisoRol)
                    .values(rol_nombre='tecnico', permiso=p)
                    .on_conflict_do_nothing()
                )
                s.execute(stmt)

        s.commit()


def obtener_permisos_usuario(usuario_rol):
    """Get the list of permissions for a given role name."""
    # Admin siempre tiene todo (seguridad)
    if usuario_rol == 'admin':
        return PERMISOS_ADMIN

    with get_session() as s:
        rows = s.scalars(
            select(PermisoRol.permiso).where(PermisoRol.rol_nombre == usuario_rol)
        ).all()
        return list(rows)


def tiene_permiso(permiso):
    """Check if the current session user has a specific permission."""
    rol = session.get('rol', '')
    if rol == 'admin':
        return True
    permisos = session.get('permisos', [])
    return permiso in permisos


# ─── Decorators ──────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            flash('Debes iniciar sesion para acceder a esta pagina.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(rol_requerido):
    """Legacy decorator — checks rol name directly."""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if session.get('rol') != rol_requerido and session.get('rol') != 'admin':
                flash('No tienes permisos para acceder a esta pagina.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def superadmin_requerido(f):
    """Sólo el SUPERADMIN DE PLATAFORMA (H1) puede acceder.

    Para superficies GLOBALES que afectan a todos los talleres (p. ej. la
    edición de roles/permisos del sistema). Un admin de taller normal recibe
    403 — NO puede tocar datos compartidos entre talleres.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not session.get("es_superadmin"):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def permiso_requerido(permiso):
    """Granular permission decorator."""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not tiene_permiso(permiso):
                flash('No tienes permisos para realizar esta accion.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
