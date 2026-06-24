"""Blueprint de administración (refactor B1).

Usuarios, roles/permisos (superadmin), auditoría, estado del sistema, prueba de
email, seed de demo y gestión de solicitudes del portal. Comportamiento idéntico
al de app.py; sólo cambian los nombres de endpoint (admin.<func>). Los roles
siguen protegidos con @superadmin_requerido.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import select, text
from werkzeug.security import generate_password_hash

import models as _models
from audit import registrar_auditoria
from auth import (
    PERMISOS_DISPONIBLES,
    login_required,
    permiso_requerido,
    superadmin_requerido,
)
from database import get_session
from models import Cliente, PermisoRol, Reparacion, Rol, SolicitudReparacion, Usuario
from pagination import paginar
from services import notificador
from utils.security import csrf_protect, validar_contraseña

logger = logging.getLogger("androtech")

bp = Blueprint("admin", __name__)


def _mail_configured():
    """Recalcula si el SMTP está configurado (leído de current_app.config)."""
    c = current_app.config
    pwd = c.get("MAIL_PASSWORD") or ""
    return bool(c.get("MAIL_USERNAME") and pwd and len(pwd) >= 12)


# =========================================
# 🔸 ADMINISTRACIÓN DE USUARIOS
# =========================================

# LISTAR USUARIOS
@bp.route("/admin/usuarios")
@login_required
@permiso_requerido('usuarios_ver')
def admin_usuarios():
    # Fase 2.4: listado de usuarios del taller activo. La subquery de
    # intervenciones también filtra por taller (mismo nombre de técnico podría
    # existir en otro taller).
    from sqlalchemy import text as _text
    with get_session() as s:
        usuarios = s.execute(_text("""
            SELECT id, usuario, rol,
                   (SELECT COUNT(*) FROM reparaciones_historial
                    WHERE usuario = usuarios.usuario AND taller_id = :tid) AS intervenciones
            FROM usuarios
            WHERE taller_id = :tid
            ORDER BY usuario ASC
        """), {"tid": g.taller_id}).mappings().all()

    try:
        logger.info(json.dumps({
            "event": "admin_usuarios_viewed",
            "admin": session.get('usuario'),
            "total_usuarios": len(usuarios)
        }, ensure_ascii=False))
    except Exception:
        logger.info(f"admin_usuarios_viewed by {session.get('usuario')}")

    return render_template("admin_usuarios.html", usuarios=usuarios)


# CREAR USUARIO
@bp.route("/admin/usuarios/nuevo", methods=["GET", "POST"])
@login_required
@permiso_requerido('usuarios_crear')
@csrf_protect
def nuevo_usuario():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        contraseña = request.form.get("contraseña", "").strip()
        rol = request.form.get("rol", "tecnico").strip()

        # Validaciones
        if not usuario or len(usuario) < 3:
            flash("❌ Usuario debe tener al menos 3 caracteres.", "danger")
            return render_template("nuevo_usuario.html")

        if not contraseña:
            flash("❌ La contraseña es obligatoria.", "danger")
            return render_template("nuevo_usuario.html")

        pwd_ok, pwd_msg = validar_contraseña(contraseña)
        if not pwd_ok:
            flash(f"❌ {pwd_msg}", "danger")
            return render_template("nuevo_usuario.html")

        with get_session() as s:
            roles_validos = list(s.scalars(select(Rol.nombre)).all())
            if rol not in roles_validos:
                flash("Rol invalido.", "danger")
                roles_db = s.scalars(select(Rol).order_by(Rol.nombre)).all()
                return render_template("nuevo_usuario.html", roles=roles_db)

            try:
                hashed_pwd = generate_password_hash(contraseña)
                s.add(Usuario(usuario=usuario, password=hashed_pwd, rol=rol))
                s.commit()

                # Registrar auditoría
                registrar_auditoria('usuario_created', session.get('usuario'), {
                    'nuevo_usuario': usuario,
                    'rol': rol
                }, ip_address=request.remote_addr)

                try:
                    logger.info(json.dumps({
                        "event": "usuario_created",
                        "admin": session.get('usuario'),
                        "nuevo_usuario": usuario,
                        "rol": rol
                    }, ensure_ascii=False))
                except Exception:
                    logger.info(f"usuario_created {usuario} rol={rol}")

                flash(f"✅ Usuario '{usuario}' creado correctamente.", "success")
                return redirect(url_for("admin.admin_usuarios"))

            except Exception as e:
                s.rollback()
                logger.exception(json.dumps({"event": "usuario_create_error"}, ensure_ascii=False))
                msg = ("Ese usuario ya existe." if "UNIQUE" in str(e)
                       else "No se pudo crear el usuario. Inténtalo de nuevo.")
                flash(f"❌ {msg}", "danger")
                roles_db = s.scalars(select(Rol).order_by(Rol.nombre)).all()
                return render_template("nuevo_usuario.html", roles=roles_db)

    with get_session() as s:
        roles_db = s.scalars(select(Rol).order_by(Rol.nombre)).all()
    return render_template("nuevo_usuario.html", roles=roles_db)


# EDITAR USUARIO
@bp.route("/admin/usuarios/editar/<int:id>", methods=["GET", "POST"])
@login_required
@permiso_requerido('usuarios_editar')
@csrf_protect
def editar_usuario(id):
    with get_session() as s:
        usuario = s.get(Usuario, id)

        if not usuario:
            flash("❌ Usuario no encontrado.", "danger")
            return redirect(url_for("admin.admin_usuarios"))

        if request.method == "POST":
            rol = request.form.get("rol", "tecnico").strip()
            nueva_contraseña = request.form.get("nueva_contraseña", "").strip()

            roles_validos = list(s.scalars(select(Rol.nombre)).all())
            if rol not in roles_validos:
                flash("Rol invalido.", "danger")
                roles_db = s.scalars(select(Rol).order_by(Rol.nombre)).all()
                return render_template("editar_usuario.html", usuario=usuario, roles=roles_db)

            try:
                if nueva_contraseña:
                    pwd_ok, pwd_msg = validar_contraseña(nueva_contraseña)
                    if not pwd_ok:
                        flash(f"❌ {pwd_msg}", "danger")
                        return render_template("editar_usuario.html", usuario=usuario)

                    usuario.password = generate_password_hash(nueva_contraseña)

                usuario.rol = rol
                s.commit()

                # Registrar auditoría
                registrar_auditoria('usuario_updated', session.get('usuario'), {
                    'usuario_id': id,
                    'usuario_nombre': usuario.usuario,
                    'nuevo_rol': rol,
                    'password_changed': bool(nueva_contraseña)
                }, ip_address=request.remote_addr)

                try:
                    logger.info(json.dumps({
                        "event": "usuario_updated",
                        "admin": session.get('usuario'),
                        "usuario_id": id,
                        "usuario_nombre": usuario.usuario,
                        "nuevo_rol": rol,
                        "password_changed": bool(nueva_contraseña)
                    }, ensure_ascii=False))
                except Exception:
                    logger.info(f"usuario_updated id={id} rol={rol}")

                flash(f"✅ Usuario '{usuario.usuario}' actualizado correctamente.", "success")
                return redirect(url_for("admin.admin_usuarios"))

            except Exception:
                s.rollback()
                logger.exception(json.dumps({"event": "usuario_update_error"}, ensure_ascii=False))
                flash("❌ No se pudo actualizar el usuario. Inténtalo de nuevo.", "danger")
                roles_db = s.scalars(select(Rol).order_by(Rol.nombre)).all()
                return render_template("editar_usuario.html", usuario=usuario, roles=roles_db)

        roles_db = s.scalars(select(Rol).order_by(Rol.nombre)).all()
        return render_template("editar_usuario.html", usuario=usuario, roles=roles_db)


# BORRAR USUARIO
@bp.route("/admin/usuarios/borrar/<int:id>")
@login_required
@permiso_requerido('usuarios_borrar')
def borrar_usuario(id):
    # Validar que no sea el mismo usuario logueado
    if session.get('usuario'):
        with get_session() as s:
            usuario = s.get(Usuario, id)

            if usuario and usuario.usuario == session.get('usuario'):
                flash("❌ No puedes borrar tu propia cuenta.", "danger")
                return redirect(url_for("admin.admin_usuarios"))

            try:
                usuario_nombre = usuario.usuario if usuario else f"ID {id}"
                if usuario:
                    s.delete(usuario)
                    s.commit()

                # Registrar auditoría
                registrar_auditoria('usuario_deleted', session.get('usuario'), {
                    'usuario_id': id,
                    'usuario_nombre': usuario_nombre
                }, ip_address=request.remote_addr)

                try:
                    logger.info(json.dumps({
                        "event": "usuario_deleted",
                        "admin": session.get('usuario'),
                        "usuario_id": id,
                        "usuario_nombre": usuario_nombre
                    }, ensure_ascii=False))
                except Exception:
                    logger.info(f"usuario_deleted id={id}")

                flash(f"✅ Usuario '{usuario_nombre}' eliminado correctamente.", "success")

            except Exception:
                s.rollback()
                logger.exception(json.dumps({"event": "usuario_delete_error"}, ensure_ascii=False))
                flash("❌ No se pudo eliminar el usuario. Inténtalo de nuevo.", "danger")

    return redirect(url_for("admin.admin_usuarios"))

# =========================================
# 🔸 GESTIÓN DE ROLES Y PERMISOS
# =========================================

@bp.route("/admin/roles")
@login_required
@superadmin_requerido
def admin_roles():
    from sqlalchemy import func as _func
    with get_session() as s:
        roles = s.scalars(
            select(Rol).order_by(Rol.es_sistema.desc(), Rol.nombre)
        ).all()
        roles_list = []
        for r in roles:
            permisos_list = list(s.scalars(
                select(PermisoRol.permiso).where(PermisoRol.rol_nombre == r.nombre)
            ).all())
            # Contar usuarios con este rol
            count = s.scalar(
                select(_func.count()).select_from(Usuario)
                .where(Usuario.rol == r.nombre)
            )
            roles_list.append({
                'id': r.id,
                'nombre': r.nombre,
                'descripcion': r.descripcion,
                'es_sistema': r.es_sistema,
                'color': r.color,
                'permisos': permisos_list,
                'num_permisos': len(permisos_list),
                'num_usuarios': count,
            })

    # Agrupar permisos por categoria
    categorias = {}
    for p in PERMISOS_DISPONIBLES:
        cat = p['categoria']
        if cat not in categorias:
            categorias[cat] = []
        categorias[cat].append(p)

    return render_template("admin_roles.html",
                           roles=roles_list,
                           categorias=categorias,
                           permisos_disponibles=PERMISOS_DISPONIBLES)


@bp.route("/admin/roles/nuevo", methods=["GET", "POST"])
@login_required
@superadmin_requerido
@csrf_protect
def nuevo_rol():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip().lower()
        descripcion = request.form.get("descripcion", "").strip()
        color = request.form.get("color", "#6c757d").strip()
        permisos = request.form.getlist("permisos")

        if not nombre or len(nombre) < 3:
            flash("El nombre del rol debe tener al menos 3 caracteres.", "danger")
            return redirect(url_for('admin.nuevo_rol'))

        if nombre in ('admin',):
            flash("No puedes crear un rol con ese nombre reservado.", "danger")
            return redirect(url_for('admin.nuevo_rol'))

        from database import insert_or_ignore
        with get_session() as s:
            try:
                s.add(Rol(nombre=nombre, descripcion=descripcion,
                          es_sistema=0, color=color))
                for p in permisos:
                    s.execute(
                        insert_or_ignore(PermisoRol)
                        .values(rol_nombre=nombre, permiso=p)
                        .on_conflict_do_nothing()
                    )
                s.commit()

                registrar_auditoria('rol_created', session.get('usuario'), {
                    'rol': nombre, 'permisos': permisos
                }, ip_address=request.remote_addr)

                flash(f"Rol '{nombre}' creado correctamente con {len(permisos)} permisos.", "success")
                return redirect(url_for('admin.admin_roles'))
            except Exception as e:
                s.rollback()
                logger.exception(json.dumps({"event": "rol_create_error"}, ensure_ascii=False))
                msg = ("Ese rol ya existe." if "UNIQUE" in str(e)
                       else "No se pudo crear el rol. Inténtalo de nuevo.")
                flash(msg, "danger")
                return redirect(url_for('admin.nuevo_rol'))

    categorias = {}
    for p in PERMISOS_DISPONIBLES:
        cat = p['categoria']
        if cat not in categorias:
            categorias[cat] = []
        categorias[cat].append(p)

    return render_template("nuevo_rol.html", categorias=categorias)


@bp.route("/admin/roles/editar/<int:id>", methods=["GET", "POST"])
@login_required
@superadmin_requerido
@csrf_protect
def editar_rol(id):
    from sqlalchemy import delete as _delete
    with get_session() as s:
        rol = s.get(Rol, id)
        if not rol:
            flash("Rol no encontrado.", "danger")
            return redirect(url_for('admin.admin_roles'))

        if request.method == "POST":
            descripcion = request.form.get("descripcion", "").strip()
            color = request.form.get("color", "#6c757d").strip()
            permisos = request.form.getlist("permisos")

            # Admin siempre tiene todos los permisos
            if rol.nombre == 'admin':
                permisos = [p['clave'] for p in PERMISOS_DISPONIBLES]

            try:
                rol.descripcion = descripcion
                rol.color = color
                # Reemplazar permisos
                s.execute(_delete(PermisoRol).where(PermisoRol.rol_nombre == rol.nombre))
                for p in permisos:
                    s.add(PermisoRol(rol_nombre=rol.nombre, permiso=p))
                s.commit()

                registrar_auditoria('rol_updated', session.get('usuario'), {
                    'rol': rol.nombre, 'permisos': permisos
                }, ip_address=request.remote_addr)

                flash(f"Rol '{rol.nombre}' actualizado correctamente.", "success")
                return redirect(url_for('admin.admin_roles'))
            except Exception:
                s.rollback()
                logger.exception(json.dumps({"event": "rol_update_error"}, ensure_ascii=False))
                flash("No se pudo actualizar el rol. Inténtalo de nuevo.", "danger")
                return redirect(url_for('admin.editar_rol', id=id))

        # GET — cargar permisos actuales
        permisos_list = list(s.scalars(
            select(PermisoRol.permiso).where(PermisoRol.rol_nombre == rol.nombre)
        ).all())

    categorias = {}
    for p in PERMISOS_DISPONIBLES:
        cat = p['categoria']
        if cat not in categorias:
            categorias[cat] = []
        categorias[cat].append(p)

    return render_template("editar_rol.html", rol=rol, permisos_actuales=permisos_list,
                           categorias=categorias)


@bp.route("/admin/roles/borrar/<int:id>")
@login_required
@superadmin_requerido
def borrar_rol(id):
    from sqlalchemy import delete as _delete
    from sqlalchemy import func as _func
    with get_session() as s:
        rol = s.get(Rol, id)
        if not rol:
            flash("Rol no encontrado.", "danger")
            return redirect(url_for('admin.admin_roles'))

        if rol.es_sistema:
            flash("No puedes eliminar roles del sistema (admin, tecnico).", "danger")
            return redirect(url_for('admin.admin_roles'))

        # Verificar que no haya usuarios con este rol
        users_count = s.scalar(
            select(_func.count()).select_from(Usuario).where(Usuario.rol == rol.nombre)
        )
        if users_count > 0:
            flash(f"No puedes eliminar el rol '{rol.nombre}' porque tiene {users_count} usuario(s) asignado(s). Reasignalos primero.", "danger")
            return redirect(url_for('admin.admin_roles'))

        rol_nombre = rol.nombre
        s.execute(_delete(PermisoRol).where(PermisoRol.rol_nombre == rol_nombre))
        s.delete(rol)
        s.commit()

    registrar_auditoria('rol_deleted', session.get('usuario'), {
        'rol': rol_nombre
    }, ip_address=request.remote_addr)

    flash(f"Rol '{rol_nombre}' eliminado correctamente.", "success")
    return redirect(url_for('admin.admin_roles'))


# (Escaparate y portal público movidos a blueprints/publico.py — refactor B1.)


# =========================================
# ADMIN: RECURSOS DE DEFENSA
# =========================================

# NOTA (B7): las rutas legacy del TFG (/admin/defensa, /docs, /docs-view) que
# servían la memoria/presentación se ELIMINARON de la rama SaaS — el TFG vive en
# su propio despliegue. No pertenecen al producto comercial.


# =========================================
# ADMIN: AUDITORÍA (vista completa paginada, B5)
# =========================================
@bp.route("/admin/auditoria")
@login_required
def admin_auditoria():
    if session.get("rol") != "admin":
        flash("Acceso restringido al administrador.", "danger")
        return redirect(url_for("dashboard"))
    from sqlalchemy import func as _func

    from models import AuditLog
    # COUNT y SELECT auto-scoped por el filtro ORM (g.taller_id): un admin sólo
    # ve los eventos de SU taller (los de plataforma con taller_id NULL no
    # cuentan para un taller). audit_log puede crecer mucho → paginado.
    with get_session() as s:
        total = s.scalar(select(_func.count(AuditLog.id)))
        pag = paginar(total)
        filas = s.scalars(
            select(AuditLog)
            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            .limit(pag.per_page).offset(pag.offset)
        ).all()
        eventos = [{
            "id": e.id, "event_type": e.event_type, "usuario": e.usuario,
            "evento_datos": e.evento_datos, "ip_address": e.ip_address,
            "timestamp": e.timestamp,
        } for e in filas]
    return render_template("admin_auditoria.html", eventos=eventos,
                           pagina=pag, filters_query="")


# =========================================
# ADMIN: SEED DE DATOS DEMO (ejecutar UNA VEZ desde el navegador)
# =========================================

@bp.route('/admin/seed-demo')
@login_required
def admin_seed_demo():
    """
    Inserta datos de demo en la BD si no existen.
    Solo accesible para admin y protegido con una clave en la URL.
    Pensado para poblar la BD efimera de Railway tras un redeploy.
    """
    if session.get('rol') != 'admin':
        flash('Acceso restringido al administrador.', 'danger')
        return redirect(url_for('dashboard'))

    SEED_KEY = os.environ.get("SEED_KEY", "demo2026")
    if request.args.get('key') != SEED_KEY:
        return ("<h3>Acceso denegado</h3>"
                "<p>Falta la clave en la URL: "
                "<code>/admin/seed-demo?key=...</code></p>"), 403

    CLIENTES = [
        ("Juan Pérez",     "634 112 233", "juan.perez@gmail.com",      "Calle Real 12, Ciudad Demo"),
        ("María García",   "612 445 667", "maria.garcia@hotmail.com",  "Av. Andalucía 45, Ciudad Demo"),
        ("Carlos López",   "698 334 112", "carlos.lopez@gmail.com",    "C/ Tartessos 8, Ciudad Demo"),
        ("Ana Martínez",   "677 223 445", "ana.martinez@gmail.com",    "Plaza del Punto 3, Ciudad Demo"),
        ("Pedro Sánchez",  "655 778 990", "pedro.sanchez@outlook.com", "C/ Cristóbal Colón 22, Ciudad Demo"),
    ]

    REPARACIONES = [
        ("Juan Pérez",    "iPhone 12",            "Pantalla rota",       "Entregado",  89.99, "Pagado",    "Stripe",   75, 60),
        ("María García",  "Samsung Galaxy A52",   "Bateria agotada",     "Terminado",  45.00, "Pendiente", None,       20, 5),
        ("Carlos López",  "MacBook Air",          "Teclado no responde", "En proceso", 120.00, "Pendiente", None,      15, None),
        ("Ana Martínez",  "Xiaomi Redmi Note 10", "No carga",            "Pendiente",  35.00, "Pendiente", None,       3,  None),
        ("Juan Pérez",    "iPad Pro",             "Pantalla rota",       "Terminado",  150.00, "Pagado",   "Efectivo", 30, 7),
        ("Pedro Sánchez", "Huawei P30",           "Camara no funciona",  "En proceso", 65.00, "Pendiente", None,       10, None),
        ("María García",  "HP Pavilion",          "Va muy lento",        "Pendiente",  None,  "Pendiente", None,       2,  None),
        ("Carlos López",  "OnePlus 9",            "Se apaga solo",       "Entregado",  55.00, "Pagado",    "Bizum",    50, 35),
    ]

    PIEZAS = [
        ("Pantalla iPhone 12",      "Pantallas",   3, 2, 45.00, 75.00, "Mobile Spain SL"),
        ("Bateria Samsung A52",     "Baterias",    5, 3, 18.00, 35.00, "ElectroParts"),
        ("Bateria iPhone generica", "Baterias",    1, 2, 12.00, 25.00, "ChinaTech"),
        ("Cargador USB-C",          "Accesorios",  8, 2,  5.00, 15.00, "ElectroParts"),
        ("Pantalla Xiaomi Redmi",   "Pantallas",   2, 2, 35.00, 60.00, "Mobile Spain SL"),
        ("Pasta termica",           "Consumibles", 10, 3, 2.00,  8.00, "ChinaTech"),
    ]

    NOTAS = [
        ("Carlos López", "MacBook Air",
         "admin",
         "Cliente avisado por telefono: pieza pedida, llegara en 5 dias laborables.",
         1),
        ("Pedro Sánchez", "Huawei P30",
         "admin",
         "Modulo de camara averiado, presupuesto adicional aceptado por el cliente.",
         0),
    ]

    def fmt(dt):
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    inserted = {"clientes": 0, "reparaciones": 0, "historial": 0, "piezas": 0, "notas": 0}
    updated = {"clientes": 0}
    skipped = {"reparaciones": 0, "piezas": 0, "notas": 0}

    # Fase 2.4 / 3a.3: el seeding usa Connection.execute(text(...)) con
    # parámetros con nombre (:p) sobre la conexión del engine — agnóstico del
    # motor (los `?` nativos sólo valen en SQLite). Los dos INSERT que necesitan
    # el id recién creado usan RETURNING id + .scalar() (SQLite 3.35+ y Postgres).
    # SIEMBRA SOLO EL TALLER ACTIVO: todas las búsquedas de existencia filtran
    # por taller_id y todos los INSERT lo fijan. Así un admin del taller B no
    # contamina ni ve los datos del A.
    tid = g.taller_id
    s = get_session()
    dconn = s.connection()

    # ---- CLIENTES ----
    cliente_ids = {}
    for nombre, tel, email, dirc in CLIENTES:
        existing = dconn.execute(
            text("SELECT id, telefono, email, direccion FROM clientes "
                 "WHERE nombre = :nombre AND taller_id = :tid"),
            {"nombre": nombre, "tid": tid},
        ).mappings().first()
        if existing:
            cid = existing["id"]
            needs_update = (
                not existing["telefono"]
                or str(existing["telefono"]).startswith("555-")
                or not existing["email"]
                or not existing["direccion"]
            )
            if needs_update:
                dconn.execute(
                    text("UPDATE clientes SET telefono=:tel, email=:email, "
                         "direccion=:dirc WHERE id=:cid AND taller_id=:tid"),
                    {"tel": tel, "email": email, "dirc": dirc, "cid": cid, "tid": tid},
                )
                updated["clientes"] += 1
        else:
            cid = dconn.execute(
                text("INSERT INTO clientes (nombre, telefono, email, direccion, taller_id) "
                     "VALUES (:nombre, :tel, :email, :dirc, :tid) RETURNING id"),
                {"nombre": nombre, "tel": tel, "email": email, "dirc": dirc, "tid": tid},
            ).scalar()
            inserted["clientes"] += 1
        cliente_ids[nombre] = cid

    # ---- REPARACIONES + HISTORIAL ----
    now = datetime.now()
    for cli_nombre, disp, desc, estado, precio, estado_pago, metodo, dias_e, dias_s in REPARACIONES:
        cid = cliente_ids.get(cli_nombre)
        if cid is None:
            continue
        dup = dconn.execute(
            text("SELECT id FROM reparaciones WHERE cliente_id=:cid AND dispositivo=:disp "
                 "AND descripcion=:desc AND taller_id=:tid"),
            {"cid": cid, "disp": disp, "desc": desc, "tid": tid},
        ).first()
        if dup:
            skipped["reparaciones"] += 1
            continue

        fecha_entrada = fmt(now - timedelta(days=dias_e))
        fecha_salida = fmt(now - timedelta(days=dias_s)) if dias_s is not None else None
        fecha_pago = fecha_salida if estado_pago == "Pagado" else None

        rid = dconn.execute(
            text("""INSERT INTO reparaciones
               (cliente_id, dispositivo, descripcion, estado, fecha_entrada, fecha_salida,
                precio, tipo_documento, estado_pago, fecha_pago, metodo_pago, taller_id,
                codigo_publico)
               VALUES (:cid, :disp, :desc, :estado, :fe, :fs, :precio, :tipo,
                       :ep, :fp, :metodo, :tid, :codigo) RETURNING id"""),
            {"cid": cid, "disp": disp, "desc": desc, "estado": estado, "fe": fecha_entrada,
             "fs": fecha_salida, "precio": precio, "tipo": "presupuesto", "ep": estado_pago,
             "fp": fecha_pago, "metodo": metodo, "tid": tid,
             "codigo": _models.generar_codigo_publico()},
        ).scalar()
        inserted["reparaciones"] += 1

        flujo = ["Pendiente", "En proceso", "Terminado", "Entregado"]
        try:
            idx_final = flujo.index(estado)
        except ValueError:
            idx_final = 0
        t_inicio = now - timedelta(days=dias_e)
        t_fin = now - timedelta(days=dias_s) if dias_s is not None else now
        paso = (t_fin - t_inicio) / max(idx_final, 1) if idx_final > 0 and t_fin > t_inicio else timedelta(0)

        anterior = None
        for i in range(idx_final + 1):
            estado_paso = flujo[i]
            fecha_paso = fecha_entrada if i == 0 else fmt(t_inicio + paso * i)
            dconn.execute(
                text("""INSERT INTO reparaciones_historial
                   (reparacion_id, estado_anterior, estado_nuevo, fecha_cambio, usuario, taller_id)
                   VALUES (:rid, :ant, :nuevo, :fecha, :usuario, :tid)"""),
                {"rid": rid, "ant": anterior, "nuevo": estado_paso, "fecha": fecha_paso,
                 "usuario": "admin", "tid": tid},
            )
            inserted["historial"] += 1
            anterior = estado_paso

    # ---- INVENTARIO ----
    fecha_act = fmt(now)
    for nombre, cat, cant, cmin, coste, venta, prov in PIEZAS:
        existing = dconn.execute(
            text("SELECT id FROM inventario_piezas WHERE nombre = :nombre AND taller_id = :tid"),
            {"nombre": nombre, "tid": tid},
        ).first()
        if existing:
            skipped["piezas"] += 1
            continue
        dconn.execute(
            text("""INSERT INTO inventario_piezas
               (nombre, categoria, cantidad, cantidad_minima, precio_coste,
                precio_venta, proveedor, fecha_actualizacion, taller_id)
               VALUES (:nombre, :cat, :cant, :cmin, :coste, :venta, :prov, :fecha, :tid)"""),
            {"nombre": nombre, "cat": cat, "cant": cant, "cmin": cmin, "coste": coste,
             "venta": venta, "prov": prov, "fecha": fecha_act, "tid": tid},
        )
        inserted["piezas"] += 1

    # ---- NOTAS ----
    for cli_nombre, disp, usuario, contenido, imp in NOTAS:
        cid = cliente_ids.get(cli_nombre)
        if cid is None:
            continue
        rep = dconn.execute(
            text("SELECT id FROM reparaciones WHERE cliente_id=:cid AND dispositivo=:disp "
                 "AND taller_id=:tid ORDER BY id DESC LIMIT 1"),
            {"cid": cid, "disp": disp, "tid": tid},
        ).mappings().first()
        if not rep:
            continue
        rid = rep["id"]
        dup = dconn.execute(
            text("SELECT id FROM notas_reparacion WHERE reparacion_id=:rid "
                 "AND contenido=:contenido AND taller_id=:tid"),
            {"rid": rid, "contenido": contenido, "tid": tid},
        ).first()
        if dup:
            skipped["notas"] += 1
            continue
        dconn.execute(
            text("""INSERT INTO notas_reparacion
               (reparacion_id, usuario, contenido, fecha_creacion, es_importante, taller_id)
               VALUES (:rid, :usuario, :contenido, :fecha, :imp, :tid)"""),
            {"rid": rid, "usuario": usuario, "contenido": contenido, "fecha": fecha_act,
             "imp": imp, "tid": tid},
        )
        inserted["notas"] += 1

    s.commit()
    s.close()

    html = f"""
    <!doctype html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Seed demo - Kintsu</title>
      <style>
        body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 720px; margin: 60px auto; padding: 20px; color: #1a202c; }}
        h1 {{ color: #2B8AC4; }}
        .card {{ background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 12px; padding: 24px; margin: 20px 0; }}
        .ok {{ color: #28a745; font-weight: 600; }}
        ul {{ line-height: 1.9; }}
        a.btn {{ display: inline-block; background: #2B8AC4; color: white; padding: 10px 20px;
                text-decoration: none; border-radius: 8px; margin-top: 20px; }}
      </style>
    </head>
    <body>
      <h1>✓ Seed demo ejecutado</h1>
      <div class="card">
        <h3 class="ok">Insertados</h3>
        <ul>
          <li>Clientes nuevos: <b>{inserted['clientes']}</b></li>
          <li>Clientes actualizados: <b>{updated['clientes']}</b></li>
          <li>Reparaciones nuevas: <b>{inserted['reparaciones']}</b></li>
          <li>Historial de estados: <b>{inserted['historial']}</b></li>
          <li>Piezas de inventario: <b>{inserted['piezas']}</b></li>
          <li>Notas internas: <b>{inserted['notas']}</b></li>
        </ul>
        <h3>Saltados (ya existian)</h3>
        <ul>
          <li>Reparaciones: {skipped['reparaciones']}</li>
          <li>Piezas: {skipped['piezas']}</li>
          <li>Notas: {skipped['notas']}</li>
        </ul>
      </div>
      <a class="btn" href="{url_for('dashboard')}">Ir al dashboard →</a>
    </body>
    </html>
    """
    return html


# =========================================
# ADMIN: ESTADO DEL SISTEMA
# =========================================

@bp.route('/admin/sistema')
@login_required
def admin_sistema():
    """Estadisticas tecnicas del servidor en tiempo real (solo admin)."""
    if session.get('rol') != 'admin':
        flash('Acceso restringido al administrador.', 'danger')
        return redirect(url_for('dashboard'))

    import sys

    import flask as _flask

    # Version Python (sin saltos de linea)
    python_version = sys.version.split('\n')[0].strip()

    # Version Flask
    try:
        flask_version = _flask.__version__
    except Exception:
        try:
            from importlib.metadata import version as _v
            flask_version = _v('flask')
        except Exception:
            flask_version = 'desconocida'

    # Numero total de rutas
    total_rutas = len(current_app.url_map._rules)

    # Tamano BD en KB
    db_path = "database/andro_tech.db"
    try:
        db_size_kb = round(os.path.getsize(db_path) / 1024, 2)
    except OSError:
        db_size_kb = 0

    # Conteo de registros por tabla del TALLER ACTIVO (Fase 2.4: filtro manual;
    # nombres de tabla fijos del bucle, no input externo). Las 4 tablas tienen
    # taller_id, así que el conteo es por taller.
    from sqlalchemy import text as _text
    tp = {"tid": g.taller_id}
    tablas_conteo = {}
    with get_session() as s:
        for tabla in ('clientes', 'reparaciones', 'usuarios', 'audit_log'):
            try:
                tablas_conteo[tabla] = s.execute(
                    _text(f"SELECT COUNT(*) FROM {tabla} WHERE taller_id = :tid"), tp
                ).scalar()
            except Exception:
                tablas_conteo[tabla] = None

        # Ultimo evento del audit_log del taller
        ultimo_evento = None
        try:
            row = s.execute(_text(
                "SELECT event_type, timestamp FROM audit_log WHERE taller_id = :tid ORDER BY id DESC LIMIT 1"
            ), tp).mappings().first()
            if row:
                ultimo_evento = {
                    'event_type': row['event_type'],
                    'timestamp': row['timestamp'],
                }
        except Exception:
            ultimo_evento = None

    # Fecha y hora actual del servidor
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Memoria del proceso (psutil opcional)
    memoria_mb = None
    psutil_disponible = False
    try:
        import psutil  # type: ignore
        proc = psutil.Process(os.getpid())
        memoria_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
        psutil_disponible = True
    except Exception:
        psutil_disponible = False

    return render_template(
        'admin_sistema.html',
        python_version=python_version,
        flask_version=flask_version,
        total_rutas=total_rutas,
        db_size_kb=db_size_kb,
        tablas_conteo=tablas_conteo,
        ultimo_evento=ultimo_evento,
        ahora=ahora,
        memoria_mb=memoria_mb,
        psutil_disponible=psutil_disponible,
        mail_configured=_mail_configured(),
        mail_username=current_app.config.get('MAIL_USERNAME') or '(no configurado)',
    )


# =========================================
# ADMIN: PROBAR ENVIO DE EMAIL
# =========================================

@bp.route('/admin/test-email', methods=['GET', 'POST'])
@login_required
def admin_test_email():
    """Enviar un email de prueba al admin para validar la config SMTP en caliente.

    - GET: muestra diagnostico de la configuracion (sin revelar la password).
    - POST: envia un email de prueba al destinatario indicado (por defecto, al
      MAIL_USERNAME configurado) y reporta el resultado via flash.
    """
    if session.get('rol') != 'admin':
        flash('Acceso restringido al administrador.', 'danger')
        return redirect(url_for('dashboard'))

    # Diagnostico (siempre visible)
    pwd_len = len(current_app.config.get('MAIL_PASSWORD') or '')
    diagnostico = {
        'server':      current_app.config.get('MAIL_SERVER'),
        'port':        current_app.config.get('MAIL_PORT'),
        'tls':         current_app.config.get('MAIL_USE_TLS'),
        'ssl':         current_app.config.get('MAIL_USE_SSL'),
        'username':    current_app.config.get('MAIL_USERNAME') or '(vacio)',
        'sender':      current_app.config.get('MAIL_DEFAULT_SENDER') or '(vacio)',
        'pwd_length':  pwd_len,
        'configured':  _mail_configured(),
    }

    if request.method == 'POST':
        # CSRF
        if request.form.get('csrf_token') != session.get('csrf_token'):
            flash('Token CSRF invalido.', 'danger')
            return redirect(url_for('admin.admin_test_email'))

        destinatario = (request.form.get('destinatario') or '').strip() \
                       or current_app.config.get('MAIL_USERNAME')

        if not destinatario or '@' not in destinatario:
            flash('Introduce un email de destino valido.', 'warning')
            return redirect(url_for('admin.admin_test_email'))

        if not _mail_configured():
            flash(
                'SMTP no configurado: revisa MAIL_USERNAME y MAIL_PASSWORD (16 caracteres, App Password de Google).',
                'danger',
            )
            return redirect(url_for('admin.admin_test_email'))

        try:
            notificador.enviar_email("send_test",
                to_email=destinatario,
                cliente_nombre=session.get('usuario', 'administrador'),
            )
            logger.info(f'[TEST-EMAIL] Enviado a {destinatario} por {session.get("usuario")}')
            flash(f'Email de prueba enviado correctamente a {destinatario}. Revisa la bandeja de entrada (y spam).', 'success')
        except socket.timeout:
            logger.error('[TEST-EMAIL] Timeout conectando a SMTP (20s)')
            flash(
                'Timeout: el servidor SMTP no respondio en 20s. '
                'Verifica que MAIL_SERVER/MAIL_PORT son correctos y que el host alcance a smtp.gmail.com.',
                'danger',
            )
        except Exception as e:
            # Traducimos los errores mas frecuentes de Gmail a mensajes utiles
            err_type = type(e).__name__
            err_msg  = str(e)
            ayuda = ''
            if '534' in err_msg or 'Application-specific password' in err_msg:
                ayuda = ' → Genera una App Password en https://myaccount.google.com/apppasswords (requiere 2FA).'
            elif '535' in err_msg or 'Username and Password not accepted' in err_msg:
                ayuda = ' → La App Password es incorrecta o la cuenta esta bloqueada.'
            elif 'timed out' in err_msg.lower() or 'timeout' in err_msg.lower():
                ayuda = ' → El servidor no responde. Comprueba firewall/antivirus o si smtp.gmail.com esta accesible.'
            logger.error(f'[TEST-EMAIL] Fallo: {err_type}: {err_msg}')
            flash(f'Error enviando email: {err_type} — {err_msg[:160]}{ayuda}', 'danger')
        return redirect(url_for('admin.admin_test_email'))

    return render_template('admin_test_email.html', diagnostico=diagnostico)


# =========================================
# ADMIN: GESTIONAR SOLICITUDES
# =========================================

@bp.route("/admin/solicitudes")
@login_required
@permiso_requerido('reparaciones_ver')
def admin_solicitudes():
    """Panel admin para ver y gestionar solicitudes de reparacion."""
    estado_filtro = request.args.get("estado", "todas")
    from sqlalchemy import func as _func

    with get_session() as s:
        # ⚠️ select(Model.__table__) es Core → el filtro automático NO se aplica.
        # Filtro de taller MANUAL (Fase 2.5).
        stmt = select(SolicitudReparacion.__table__).where(
            SolicitudReparacion.__table__.c.taller_id == g.taller_id
        )
        if estado_filtro and estado_filtro != "todas":
            stmt = stmt.where(SolicitudReparacion.__table__.c.estado == estado_filtro)
        stmt = stmt.order_by(SolicitudReparacion.__table__.c.fecha_solicitud.desc())
        solicitudes = s.execute(stmt).mappings().all()

        # Contadores
        def _count(estado=None):
            q = select(_func.count()).select_from(SolicitudReparacion)
            if estado:
                q = q.where(SolicitudReparacion.estado == estado)
            return s.scalar(q)

        total = _count()
        pendientes = _count('pendiente')
        aceptadas = _count('aceptada')
        rechazadas = _count('rechazada')

    return render_template("admin_solicitudes.html",
        solicitudes=solicitudes,
        estado_filtro=estado_filtro,
        total=total,
        pendientes=pendientes,
        aceptadas=aceptadas,
        rechazadas=rechazadas
    )


@bp.route("/admin/solicitudes/<int:id>/aceptar", methods=["POST"])
@login_required
@csrf_protect
@permiso_requerido('reparaciones_crear')
def aceptar_solicitud(id):
    """Aceptar una solicitud y crear cliente + reparacion automaticamente."""
    from sqlalchemy import func as _func
    with get_session() as s:
        solicitud = s.get(SolicitudReparacion, id)

        if not solicitud:
            flash("Solicitud no encontrada.", "danger")
            return redirect(url_for("admin.admin_solicitudes"))

        # Buscar si ya existe un cliente con ese telefono o email
        cliente = None
        if solicitud.email:
            cliente = s.scalars(
                select(Cliente).where(_func.lower(Cliente.email) == solicitud.email.lower())
            ).first()
        if not cliente and solicitud.telefono:
            cliente = s.scalars(
                select(Cliente).where(Cliente.telefono == solicitud.telefono)
            ).first()

        if cliente:
            cliente_id = cliente.id
        else:
            # Crear nuevo cliente
            nuevo_cli = Cliente(nombre=solicitud.nombre,
                                telefono=solicitud.telefono,
                                email=solicitud.email)
            s.add(nuevo_cli)
            s.flush()  # asigna el id sin commitear (equivale a last_insert_rowid)
            cliente_id = nuevo_cli.id

        # Crear reparacion
        dispositivo_str = solicitud.dispositivo
        if solicitud.marca:
            dispositivo_str += f" {solicitud.marca}"
        if solicitud.modelo:
            dispositivo_str += f" {solicitud.modelo}"

        nueva_rep = Reparacion(
            cliente_id=cliente_id, dispositivo=dispositivo_str,
            descripcion=solicitud.descripcion, estado='Pendiente',
            fecha_entrada=datetime.now().strftime("%Y-%m-%d"),
        )
        s.add(nueva_rep)
        s.flush()
        reparacion_id = nueva_rep.id

        # Marcar solicitud como aceptada
        notas = request.form.get("notas_admin", "").strip()
        solicitud.estado = 'aceptada'
        solicitud.notas_admin = notas
        solicitud.fecha_gestion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        solicitud_nombre = solicitud.nombre
        s.commit()

    flash(f"Solicitud aceptada. Se creo la reparacion #{reparacion_id} para {solicitud_nombre}.", "success")
    return redirect(url_for("admin.admin_solicitudes"))


@bp.route("/admin/solicitudes/<int:id>/rechazar", methods=["POST"])
@login_required
@csrf_protect
@permiso_requerido('reparaciones_ver')
def rechazar_solicitud(id):
    """Rechazar una solicitud."""
    notas = request.form.get("notas_admin", "").strip()
    with get_session() as s:
        solicitud = s.get(SolicitudReparacion, id)
        if solicitud:
            solicitud.estado = 'rechazada'
            solicitud.notas_admin = notas
            solicitud.fecha_gestion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            s.commit()

    flash("Solicitud rechazada.", "warning")
    return redirect(url_for("admin.admin_solicitudes"))


@bp.route("/admin/solicitudes/<int:id>/borrar", methods=["POST"])
@login_required
@csrf_protect
@permiso_requerido('reparaciones_borrar')
def borrar_solicitud(id):
    """Eliminar una solicitud."""
    with get_session() as s:
        solicitud = s.get(SolicitudReparacion, id)
        if solicitud:
            s.delete(solicitud)
            s.commit()
    flash("Solicitud eliminada.", "info")
    return redirect(url_for("admin.admin_solicitudes"))
