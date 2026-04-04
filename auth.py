"""Authentication, authorization and permissions.

This module contains decorators for login, role enforcement and
granular permission checks. It also defines the default permissions
for the built-in roles ('admin' and 'tecnico').
"""

from functools import wraps
from flask import session, redirect, url_for, flash

from db import get_db

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


def init_permisos_db(conn):
    """Create permissions tables and seed default roles."""
    # Tabla de roles
    conn.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            descripcion TEXT,
            es_sistema INTEGER DEFAULT 0,
            color TEXT DEFAULT '#6c757d'
        )
    """)

    # Tabla de permisos por rol
    conn.execute("""
        CREATE TABLE IF NOT EXISTS permisos_rol (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rol_nombre TEXT NOT NULL,
            permiso TEXT NOT NULL,
            UNIQUE(rol_nombre, permiso)
        )
    """)
    conn.commit()

    # Insertar roles base si no existen
    existing = conn.execute("SELECT nombre FROM roles").fetchall()
    existing_names = [r['nombre'] if isinstance(r, dict) or hasattr(r, 'keys') else r[0] for r in existing]

    if 'admin' not in existing_names:
        conn.execute(
            "INSERT INTO roles (nombre, descripcion, es_sistema, color) VALUES (?, ?, 1, ?)",
            ('admin', 'Acceso completo al sistema. No se puede eliminar.', '#dc3545')
        )
        for p in PERMISOS_ADMIN:
            conn.execute(
                "INSERT OR IGNORE INTO permisos_rol (rol_nombre, permiso) VALUES (?, ?)",
                ('admin', p)
            )

    if 'tecnico' not in existing_names:
        conn.execute(
            "INSERT INTO roles (nombre, descripcion, es_sistema, color) VALUES (?, ?, 1, ?)",
            ('tecnico', 'Acceso a reparaciones, clientes y herramientas basicas.', '#2B8AC4')
        )
        for p in PERMISOS_TECNICO:
            conn.execute(
                "INSERT OR IGNORE INTO permisos_rol (rol_nombre, permiso) VALUES (?, ?)",
                ('tecnico', p)
            )

    conn.commit()


def obtener_permisos_usuario(usuario_rol):
    """Get the list of permissions for a given role name."""
    # Admin siempre tiene todo (seguridad)
    if usuario_rol == 'admin':
        return PERMISOS_ADMIN

    conn = get_db()
    rows = conn.execute(
        "SELECT permiso FROM permisos_rol WHERE rol_nombre = ?",
        (usuario_rol,)
    ).fetchall()
    conn.close()
    return [r['permiso'] if hasattr(r, 'keys') else r[0] for r in rows]


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
