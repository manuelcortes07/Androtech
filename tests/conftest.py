"""Pytest infrastructure for AndroTech smoke tests.

Diseño (DUAL-ENGINE, Fase 3a.5):
- Por defecto (sin `TEST_DATABASE_URL`) corre sobre **SQLite** en una BD
  temporal en disco — comportamiento rápido de siempre.
- Si `TEST_DATABASE_URL` está definida → corre la MISMA suite sobre
  **PostgreSQL** (p. ej. un contenedor Docker). El esquema se recrea limpio
  desde los modelos (`Base.metadata.create_all`) y `db_conn` se envuelve en
  `DualConn`, que traduce `?`→`%s` y emula `lastrowid` con `RETURNING id`,
  para no reescribir ni un test.
- `app.py` se importa una sola vez tras fijar el entorno. En SQLite se
  bootstrappean a mano las 4 tablas core que app.py no crea; en Postgres el
  arranque de la app crea todo el esquema desde los modelos.
- Cada test corre con `DELETE FROM` previo en las tablas mutables (autouse).
- Stripe y SMTP están mockeados para que ningún test toque APIs externas.
"""

import os
import sqlite3
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# ───────────────────────────────────────────────────────────────────
# Configurar entorno ANTES de importar app
# ───────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # tests/ (DualConn)

from _dbadapter import DualConn  # noqa: E402

# ¿Postgres o SQLite? Si TEST_DATABASE_URL está definida, corremos sobre
# Postgres; si no, sobre una BD SQLite temporal.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
USE_POSTGRES = bool(TEST_DATABASE_URL)

# BD temporal en disco (no :memory: porque cada conexión vería una BD
# distinta y app.py abre/cierra conexiones constantemente).
_tmp_fd, TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="androtech_test_")
os.close(_tmp_fd)

if USE_POSTGRES:
    # database.py prefiere DATABASE_URL sobre DATABASE_PATH y normaliza el
    # scheme a postgresql+psycopg://. No fijamos DATABASE_PATH.
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ.pop("DATABASE_PATH", None)
else:
    os.environ.pop("DATABASE_URL", None)
    os.environ["DATABASE_PATH"] = TEST_DB_PATH
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_dummy")
os.environ.setdefault("STRIPE_PUBLISHABLE_KEY", "pk_test_dummy")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_dummy")
os.environ.setdefault("MAIL_USERNAME", "test@example.com")
os.environ.setdefault("MAIL_PASSWORD", "dummy")
os.environ.setdefault("MAIL_DEFAULT_SENDER", "test@example.com")


# ───────────────────────────────────────────────────────────────────
# Tablas que app.py NO crea al importar
# ───────────────────────────────────────────────────────────────────
_CORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    telefono TEXT,
    email TEXT,
    direccion TEXT
);

CREATE TABLE IF NOT EXISTS reparaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER,
    dispositivo TEXT NOT NULL,
    descripcion TEXT,
    estado TEXT DEFAULT 'Pendiente',
    fecha_entrada TEXT,
    fecha_salida TEXT,
    precio REAL,
    tipo_documento TEXT DEFAULT 'presupuesto',
    estado_pago TEXT DEFAULT 'Pendiente',
    fecha_pago TEXT,
    metodo_pago TEXT,
    firma TEXT,
    codigo_publico TEXT,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL UNIQUE,
    contraseña TEXT NOT NULL,
    rol TEXT DEFAULT 'tecnico',
    es_superadmin INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reparaciones_historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reparacion_id INTEGER NOT NULL,
    estado_anterior TEXT,
    estado_nuevo TEXT NOT NULL,
    fecha_cambio TEXT NOT NULL,
    usuario TEXT,
    FOREIGN KEY (reparacion_id) REFERENCES reparaciones(id)
);
"""


def _bootstrap_core_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_CORE_SCHEMA)
    conn.commit()
    conn.close()


# URL Postgres en formato psycopg puro (sin el sufijo +psycopg de SQLAlchemy).
def _pg_raw_url() -> str:
    url = TEST_DATABASE_URL
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://"):]
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


def _reset_postgres_schema() -> None:
    """Deja el esquema `public` vacío para que el arranque de la app lo
    reconstruya limpio desde los modelos (create_all)."""
    import psycopg
    with psycopg.connect(_pg_raw_url(), autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS public CASCADE")
        c.execute("CREATE SCHEMA public")


if USE_POSTGRES:
    _reset_postgres_schema()
else:
    _bootstrap_core_schema(TEST_DB_PATH)

# Subidas a un tmpdir EFÍMERO: se fija UPLOADS_DIR *antes* de importar la app,
# así `uploads.py` (importado por app) computa UPLOAD_FOLDER/SIGNATURES_FOLDER/
# LOGO_FOLDER bajo el tmpdir y ningún test escribe en `static/uploads/` real.
# branding.py también resuelve el logo por esta env var → todo coherente.
_TEST_UPLOAD_ROOT = tempfile.mkdtemp(prefix="androtech_test_uploads_")
os.environ["UPLOADS_DIR"] = _TEST_UPLOAD_ROOT

# Ahora sí importar la app. En SQLite crea las 8 tablas restantes y siembra
# roles; en Postgres crea TODO el esquema desde los modelos + roles + taller 1.
from werkzeug.security import generate_password_hash  # noqa: E402

import app as app_module  # noqa: E402


def _raw_conn():
    """Conexión DBAPI cruda al motor activo (SQLite o Postgres)."""
    if USE_POSTGRES:
        import psycopg
        return psycopg.connect(_pg_raw_url(), autocommit=False)
    conn = sqlite3.connect(TEST_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# (Las carpetas de subida ya quedaron bajo el tmpdir vía UPLOADS_DIR fijado
# antes de importar la app — ver arriba. `uploads.py` las creó al importarse.)

# El rate limiting es infraestructura: NO debe interferir con los tests
# funcionales (que repiten POSTs a /login, /signup, etc.). Se desactiva aquí.
app_module.limiter.enabled = False


# ───────────────────────────────────────────────────────────────────
# Fixtures de Flask
# ───────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def app():
    """La instancia Flask configurada para tests."""
    app_module.app.config["TESTING"] = True
    # WTF_CSRF se gestiona a mano en este proyecto; lo desactivamos vía
    # un parche directo en utils.security.validate_csrf para que los POST
    # de los tests pasen sin token.
    yield app_module.app


@pytest.fixture
def client(app):
    """Cliente HTTP de pruebas. No autenticado."""
    return app.test_client()


@pytest.fixture
def db_conn():
    """Conexión cruda a la BD de tests envuelta en DualConn (SQLite/Postgres).

    DualConn da la misma API estilo sqlite3 (`?`, `cur.lastrowid`,
    `row["col"]`/`row[0]`) sobre cualquiera de los dos motores, así que los
    tests no cambian.
    """
    conn = DualConn(_raw_conn(), is_postgres=USE_POSTGRES)
    yield conn
    conn.close()


# ───────────────────────────────────────────────────────────────────
# Reset de datos entre tests
# ───────────────────────────────────────────────────────────────────
_DATA_TABLES = (
    "stripe_eventos",
    "taller_settings",
    "audit_log",
    "reparaciones_historial",
    "piezas_reparacion",
    "fotos_reparacion",
    "notas_reparacion",
    "solicitudes_reparacion",
    "reparaciones",
    "clientes",
    "inventario_piezas",
    "usuarios",
)


@pytest.fixture(autouse=True)
def _reset_data():
    """Borra datos antes de cada test (mantiene esquema y roles/permisos).

    El orden de `_DATA_TABLES` es FK-seguro para el DELETE (hijos antes que
    padres), necesario en Postgres donde las FKs se imponen.
    """
    conn = _raw_conn()
    for t in _DATA_TABLES:
        try:
            conn.execute(f"DELETE FROM {t}")
            conn.commit()
        except Exception:
            conn.rollback()  # tabla aún no existe / nada que borrar
    # Mantener el taller 1 ("androtech"); borrar talleres extra de tests
    # (p. ej. el taller 2 'rival' de seed_taller_2) para no colisionar.
    try:
        conn.execute("DELETE FROM talleres WHERE id != 1")
        conn.commit()
    except Exception:
        conn.rollback()
    # Resetear las columnas mutables del taller 1 (config/nif) para que el
    # branding/logo de un test no se filtre al siguiente (white-label).
    try:
        conn.execute("UPDATE talleres SET config = NULL, nif = NULL WHERE id = 1")
        conn.commit()
    except Exception:
        conn.rollback()
    conn.close()
    yield


# ───────────────────────────────────────────────────────────────────
# Sembradores de datos (helpers reusables)
# ───────────────────────────────────────────────────────────────────
@pytest.fixture
def seed_admin(db_conn):
    """Crea un usuario admin con password 'admin123'. Devuelve dict."""
    pwd_hash = generate_password_hash("admin123")
    db_conn.execute(
        'INSERT INTO usuarios (usuario, "contraseña", rol) VALUES (?, ?, ?)',
        ("admin", pwd_hash, "admin"),
    )
    db_conn.commit()
    return {"usuario": "admin", "password": "admin123", "rol": "admin"}


@pytest.fixture
def seed_tecnico(db_conn):
    """Crea un usuario tecnico con password 'tecnico123'."""
    pwd_hash = generate_password_hash("tecnico123")
    db_conn.execute(
        'INSERT INTO usuarios (usuario, "contraseña", rol) VALUES (?, ?, ?)',
        ("tecni", pwd_hash, "tecnico"),
    )
    db_conn.commit()
    return {"usuario": "tecni", "password": "tecnico123", "rol": "tecnico"}


@pytest.fixture
def seed_cliente(db_conn):
    """Crea un cliente de ejemplo y devuelve su id."""
    cur = db_conn.execute(
        "INSERT INTO clientes (nombre, telefono, email, direccion) VALUES (?, ?, ?, ?)",
        ("Cliente Test", "600111222", "test@cliente.com", "Calle Test 1, Huelva"),
    )
    db_conn.commit()
    return cur.lastrowid


@pytest.fixture
def seed_reparacion(db_conn, seed_cliente):
    """Crea una reparación de ejemplo asociada a `seed_cliente`."""
    cur = db_conn.execute(
        """INSERT INTO reparaciones
           (cliente_id, dispositivo, descripcion, estado, fecha_entrada,
            precio, estado_pago, codigo_publico)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (seed_cliente, "iPhone 12", "Pantalla rota", "Pendiente",
         "2026-01-15", 120.0, "Pendiente", "SEEDCODE12345"),
    )
    db_conn.commit()
    return cur.lastrowid


@pytest.fixture
def seed_taller_2(db_conn):
    """Crea el taller 2 'rival' con datos deliberadamente clónicos a los del
    taller 1 (mismo nombre de cliente/email, mismo usuario 'admin').

    Devuelve un dict con los ids de taller 2 para los tests de aislamiento.
    Inserta vía SQL crudo con taller_id explícito (no pasa por el auto-stamp).
    """
    db_conn.execute(
        """INSERT INTO talleres (id, nombre, slug, email_contacto, fecha_alta, estado, plan)
           VALUES (2, 'Taller Rival', 'rival', 'rival@x.com', '2026-01-01', 'activo', 'basico')"""
    )
    pwd = generate_password_hash("rivalpass")
    db_conn.execute(
        'INSERT INTO usuarios (usuario, "contraseña", rol, taller_id) VALUES (?, ?, ?, 2)',
        ("admin", pwd, "admin"),
    )
    cur = db_conn.execute(
        "INSERT INTO clientes (nombre, telefono, email, direccion, taller_id) "
        "VALUES ('Cliente Test', '600111222', 'test@cliente.com', 'Calle X', 2)"
    )
    cli2 = cur.lastrowid
    cur = db_conn.execute(
        """INSERT INTO reparaciones
           (cliente_id, dispositivo, descripcion, estado, fecha_entrada, precio, estado_pago, taller_id)
           VALUES (?, 'Pixel RIVAL', 'Secreto de B', 'Pendiente', '2026-02-01', 999.0, 'Pendiente', 2)""",
        (cli2,),
    )
    rep2 = cur.lastrowid
    cur = db_conn.execute(
        "INSERT INTO inventario_piezas (nombre, cantidad, taller_id) VALUES ('Pieza RIVAL', 7, 2)"
    )
    pieza2 = cur.lastrowid
    cur = db_conn.execute(
        """INSERT INTO solicitudes_reparacion (nombre, telefono, dispositivo, descripcion, fecha_solicitud, taller_id)
           VALUES ('Solicitante B', '699', 'Tablet', 'Algo de B', '2026-02-02', 2)"""
    )
    sol2 = cur.lastrowid
    db_conn.commit()
    return {"taller_id": 2, "slug": "rival", "cliente_id": cli2,
            "reparacion_id": rep2, "pieza_id": pieza2, "solicitud_id": sol2}


# ───────────────────────────────────────────────────────────────────
# Helpers de sesión (login sin pasar por el formulario CSRF)
# ───────────────────────────────────────────────────────────────────
@pytest.fixture
def logged_admin(client, seed_admin, app):
    """Cliente autenticado como admin (salta el formulario de login)."""
    with client.session_transaction() as sess:
        sess["usuario"] = seed_admin["usuario"]
        sess["rol"] = "admin"
        # Admin tiene todos los permisos automáticamente vía tiene_permiso(),
        # pero los rellenamos por consistencia con login() real.
        from auth import PERMISOS_ADMIN
        sess["permisos"] = PERMISOS_ADMIN
        # Fase 2.2: la sesión queda ligada al taller (el resolver lee de aquí).
        sess["taller_id"] = 1
        sess["taller_slug"] = "androtech"
        sess["csrf_token"] = "test-csrf-token"
    return client


@pytest.fixture
def logged_tecnico(client, seed_tecnico, app):
    """Cliente autenticado como técnico (con permisos por defecto)."""
    with client.session_transaction() as sess:
        sess["usuario"] = seed_tecnico["usuario"]
        sess["rol"] = "tecnico"
        from auth import PERMISOS_TECNICO
        sess["permisos"] = list(PERMISOS_TECNICO)
        sess["taller_id"] = 1
        sess["taller_slug"] = "androtech"
        sess["csrf_token"] = "test-csrf-token"
    return client


# ───────────────────────────────────────────────────────────────────
# Mocks de servicios externos (Stripe + email)
# ───────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _block_external_services(monkeypatch):
    """Por defecto bloqueamos cualquier llamada a SMTP y Stripe APIs.

    Los tests que necesiten interactuar con Stripe sobreescriben con sus
    propios mocks granulares.
    """
    # Bloquear envío real de email
    from utils import email_service
    monkeypatch.setattr(
        email_service.EmailService, "_send",
        lambda self, **kwargs: None
    )

    # Bloquear llamadas reales a la API de Stripe sin romper la importación
    if app_module.stripe is not None:
        fake_session = MagicMock()
        fake_session.id = "cs_test_dummy_123"
        fake_session.url = "https://stripe.test/checkout/cs_test_dummy_123"
        monkeypatch.setattr(
            app_module.stripe.checkout.Session, "create",
            lambda *a, **kw: fake_session,
        )
    yield


# Nota: el helper `stripe_webhook_event(...)` vive en test_smoke.py para
# evitar problemas de import (pytest no añade tests/ a sys.path por defecto).


# ───────────────────────────────────────────────────────────────────
# CSRF: deshabilitar validación en tests
# ───────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _disable_csrf_validation(monkeypatch):
    """Los tests no envían tokens CSRF; siempre pasan la validación."""
    from utils import security
    monkeypatch.setattr(security, "validate_csrf", lambda: True)
    # app.py importa validate_csrf directamente, así que también allí
    import app as _app
    if hasattr(_app, "validate_csrf"):
        monkeypatch.setattr(_app, "validate_csrf", lambda: True)
    yield
