"""Blueprint del dashboard + healthcheck (refactor B1).

KPIs y graficos (Chart.js) del panel del taller (~20 queries raw SQL, cada una
con filtro MANUAL taller_id=:tid porque el filtro automatico del ORM no alcanza
text()) y el endpoint /health (liveness + readiness ligero de BD). Comportamiento
identico al que tenian en app.py; solo cambia el nombre de endpoint
(dashboard -> dashboard.dashboard, healthcheck -> dashboard.healthcheck).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    g,
    jsonify,
    render_template,
    session,
)
from sqlalchemy import text

from alerts import calcular_alertas_reparacion
from audit import obtener_auditoria_reciente
from auth import login_required
from database import get_session, is_postgres

logger = logging.getLogger("androtech")

bp = Blueprint("dashboard", __name__)


def _mail_configured() -> bool:
    """¿Hay credenciales SMTP válidas? (App Password Google = 16 chars)."""
    c = current_app.config
    pwd = c.get("MAIL_PASSWORD") or ""
    return bool(c.get("MAIL_USERNAME") and pwd and len(pwd) >= 12)


# HEALTHCHECK — endpoint ligero para diagnosticar deploys en Railway.
# No toca BD, no toca SMTP, no depende de sesion. Si esto devuelve 200, el
# worker esta vivo; si devuelve 502, gunicorn no arranca.
@bp.route("/health")
def healthcheck():
    # Liveness + readiness ligero: comprueba la conexión a BD con un SELECT 1.
    # Devuelve 200 siempre (el proceso está vivo) e informa del estado de la BD
    # en "database"; así un parpadeo de BD no tira el healthcheck del hosting.
    db_ok = True
    try:
        with get_session() as s:
            s.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
        logger.warning('{"event": "health_db_unavailable"}')
    return jsonify({
        "status": "ok",
        "database": "ok" if db_ok else "unavailable",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "mail_configured": _mail_configured(),
        "python": f"{os.sys.version_info.major}.{os.sys.version_info.minor}",
    }), 200


@bp.route("/dashboard")
@login_required
def dashboard():
    # Fase 2.4: las ~20 queries del dashboard son raw SQL → NO las alcanza el
    # filtro automático del ORM. Cada una lleva el filtro MANUAL taller_id=:tid.
    from sqlalchemy import text as _text
    tp = {"tid": g.taller_id}
    s = get_session()

    # ========== ESTADÍSTICAS GENERALES ==========
    total_clientes = s.execute(_text("SELECT COUNT(*) FROM clientes WHERE taller_id = :tid"), tp).scalar()
    total_reparaciones = s.execute(_text("SELECT COUNT(*) FROM reparaciones WHERE taller_id = :tid"), tp).scalar()

    reparaciones_activas = s.execute(_text("""
        SELECT COUNT(*) FROM reparaciones
        WHERE taller_id = :tid AND estado != 'Terminado' AND estado != 'Entregado'
    """), tp).scalar()

    reparaciones_terminadas = s.execute(_text("""
        SELECT COUNT(*) FROM reparaciones
        WHERE taller_id = :tid AND (estado = 'Terminado' OR estado = 'Entregado')
    """), tp).scalar()

    # Ingresos totales
    ingresos_total = s.execute(_text("""
        SELECT COALESCE(SUM(precio), 0) FROM reparaciones
        WHERE taller_id = :tid AND precio IS NOT NULL
    """), tp).scalar()

    # ========== ESTADÍSTICAS DE ESTE MES ==========
    hoy = datetime.now()
    inicio_mes = datetime(hoy.year, hoy.month, 1)

    ingresos_mes = s.execute(_text("""
        SELECT COALESCE(SUM(precio), 0) FROM reparaciones
        WHERE taller_id = :tid AND fecha_entrada >= :inicio AND precio IS NOT NULL
    """), {**tp, "inicio": inicio_mes.strftime("%Y-%m-%d")}).scalar()

    reparaciones_mes = s.execute(_text("""
        SELECT COUNT(*) FROM reparaciones
        WHERE taller_id = :tid AND fecha_entrada >= :inicio
    """), {**tp, "inicio": inicio_mes.strftime("%Y-%m-%d")}).scalar()

    reparaciones_completadas_mes = s.execute(_text("""
        SELECT COUNT(*) FROM reparaciones
        WHERE taller_id = :tid AND (estado = 'Terminado' OR estado = 'Entregado')
        AND fecha_entrada >= :inicio
    """), {**tp, "inicio": inicio_mes.strftime("%Y-%m-%d")}).scalar()

    # ========== ESTADÍSTICAS DE PAGOS ==========
    dinero_cobrado = s.execute(_text("""
        SELECT COALESCE(SUM(precio), 0) FROM reparaciones
        WHERE taller_id = :tid AND estado_pago = 'Pagado' AND precio IS NOT NULL
    """), tp).scalar()

    dinero_por_cobrar = ingresos_total - dinero_cobrado

    reparaciones_pendiente_pago = s.execute(_text("""
        SELECT COUNT(*) FROM reparaciones
        WHERE taller_id = :tid AND estado_pago = 'Pendiente' AND precio IS NOT NULL AND precio > 0
    """), tp).scalar()

    reparaciones_pagadas = s.execute(_text("""
        SELECT COUNT(*) FROM reparaciones
        WHERE taller_id = :tid AND estado_pago = 'Pagado'
    """), tp).scalar()

    # Calcular tasa de cobro (porcentaje)
    tasa_cobro = 0
    if ingresos_total > 0:
        tasa_cobro = round((dinero_cobrado / ingresos_total * 100), 1)

    # Obtener reparaciones pendientes de pago (últimas 5)
    reparaciones_sin_pagar = s.execute(_text("""
        SELECT reparaciones.*, clientes.nombre AS cliente
        FROM reparaciones
        LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id
        WHERE reparaciones.taller_id = :tid AND reparaciones.estado_pago = 'Pendiente'
        AND reparaciones.precio IS NOT NULL AND reparaciones.precio > 0
        ORDER BY reparaciones.id DESC
        LIMIT 5
    """), tp).mappings().all()
    reparaciones_sin_pagar_list = [dict(r) for r in reparaciones_sin_pagar] if reparaciones_sin_pagar else []

    # ========== DISPOSITIVOS MÁS REPARADOS ==========
    dispositivos_top = s.execute(_text("""
        SELECT dispositivo, COUNT(*) as cantidad
        FROM reparaciones
        WHERE taller_id = :tid AND dispositivo IS NOT NULL AND dispositivo != ''
        GROUP BY dispositivo
        ORDER BY cantidad DESC, dispositivo ASC
        LIMIT 5
    """), tp).all()

    # ========== ESTADOS MÁS COMUNES ==========
    estados_distribucion = s.execute(_text("""
        SELECT estado, COUNT(*) as cantidad
        FROM reparaciones
        WHERE taller_id = :tid
        GROUP BY estado
        ORDER BY cantidad DESC, estado ASC
    """), tp).all()

    # Convertir a dict para template
    dispositivos_dict = [{"nombre": d[0], "cantidad": d[1]} for d in dispositivos_top] if dispositivos_top else []
    estados_dict = [{"nombre": e[0], "cantidad": e[1]} for e in estados_distribucion] if estados_distribucion else []

    # Calcular porcentajes
    total_rep = reparaciones_activas + reparaciones_terminadas
    porcentaje_activas = round((reparaciones_activas / total_rep * 100), 1) if total_rep > 0 else 0
    porcentaje_terminadas = round((reparaciones_terminadas / total_rep * 100), 1) if total_rep > 0 else 0

    # Últimas 5 reparaciones
    ultimas_reparaciones = s.execute(_text("""
        SELECT reparaciones.*, clientes.nombre AS cliente
        FROM reparaciones
        LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id
        WHERE reparaciones.taller_id = :tid
        ORDER BY reparaciones.id DESC
        LIMIT 5
    """), tp).mappings().all()

    # ========== REPARACIONES ATRASADAS (sin actualización hace > 7 días) ==========
    hace_7_dias = (hoy - __import__('datetime').timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    # ⚠️ El filtro taller_id envuelve TODA la condición original: el OR del
    # final tiene menor precedencia, así que sin el paréntesis externo
    # `... OR (subq)=0` se saldría del scope y filtraría reparaciones de otro
    # taller sin historial. taller_id AND ( <condición original> ) lo evita.
    reparaciones_atrasadas = s.execute(_text("""
        SELECT reparaciones.*, clientes.nombre AS cliente,
               (SELECT fecha_cambio FROM reparaciones_historial
                WHERE reparacion_id = reparaciones.id
                ORDER BY fecha_cambio DESC LIMIT 1) AS ultima_actualizacion
        FROM reparaciones
        LEFT JOIN clientes ON clientes.id = reparaciones.cliente_id
        WHERE reparaciones.taller_id = :tid AND (
            reparaciones.estado IN ('En proceso', 'Pendiente')
            AND (
                SELECT fecha_cambio FROM reparaciones_historial
                WHERE reparacion_id = reparaciones.id
                ORDER BY fecha_cambio DESC LIMIT 1
            ) < :hace7
            OR (
                SELECT COUNT(*) FROM reparaciones_historial
                WHERE reparacion_id = reparaciones.id
            ) = 0
        )
        ORDER BY reparaciones.id DESC
    """), {**tp, "hace7": hace_7_dias}).mappings().all()

    reparaciones_atrasadas_list = [dict(r) for r in reparaciones_atrasadas] if reparaciones_atrasadas else []

    # Enriquecer con alertas
    for rep in reparaciones_sin_pagar_list:
        rep['alertas_info'] = calcular_alertas_reparacion(rep, rep.get('ultima_actualizacion'))

    for rep in reparaciones_atrasadas_list:
        rep['alertas_info'] = calcular_alertas_reparacion(rep, rep.get('ultima_actualizacion'))

    # ========== MÉTRICA 1: INGRESOS POR MES (últimos 6 meses) ==========
    ingresos_por_mes = []
    for i in range(5, -1, -1):  # Últimos 6 meses
        fecha = hoy - __import__('datetime').timedelta(days=30*i)
        inicio = datetime(fecha.year, fecha.month, 1)
        if i == 0:
            fin = hoy
        else:
            # Primer día del mes siguiente
            if fecha.month == 12:
                fin = datetime(fecha.year + 1, 1, 1) - __import__('datetime').timedelta(seconds=1)
            else:
                fin = datetime(fecha.year, fecha.month + 1, 1) - __import__('datetime').timedelta(seconds=1)

        ingreso_mes_i = s.execute(_text("""
            SELECT COALESCE(SUM(precio), 0) FROM reparaciones
            WHERE taller_id = :tid AND fecha_entrada >= :ini AND fecha_entrada <= :fin AND precio IS NOT NULL
        """), {**tp, "ini": inicio.strftime("%Y-%m-%d"), "fin": fin.strftime("%Y-%m-%d")}).scalar()

        ingresos_por_mes.append({
            "mes": inicio.strftime("%b %Y"),
            # float() para que el repr sea idéntico entre motores: SQLite
            # devuelve int 0 cuando no hay filas y Postgres 0.0 (mismo valor,
            # distinto repr); la coerción los iguala (Fase 3a.5, pincho A).
            "valor": round(float(ingreso_mes_i), 2)
        })

    # ========== MÉTRICA 2: TIEMPO MEDIO DE REPARACIÓN ==========
    tiempo_medio_dias = 0
    reparaciones_completadas = s.execute(_text("""
        SELECT COUNT(*) FROM reparaciones
        WHERE taller_id = :tid AND (estado = 'Terminado' OR estado = 'Entregado')
    """), tp).scalar()

    if reparaciones_completadas > 0:
        # Calcular promedio de días entre entrada y última actualización.
        # ⚠️ Pincho A: julianday() es SQLite-only. Las fechas son TEXT en ambos
        # motores; el cálculo de "días entre" se ramifica por dialecto:
        #   SQLite   → julianday(a) - julianday(b)
        #   Postgres → EXTRACT(EPOCH FROM (a::timestamp - b::timestamp)) / 86400
        if is_postgres():
            _dif_dias = ("EXTRACT(EPOCH FROM (CAST({a} AS timestamp) "
                         "- CAST(reparaciones.fecha_entrada AS timestamp))) / 86400.0")
        else:
            _dif_dias = "julianday({a}) - julianday(reparaciones.fecha_entrada)"
        _ultima = ("COALESCE((SELECT fecha_cambio FROM reparaciones_historial "
                   "WHERE reparacion_id = reparaciones.id "
                   "ORDER BY fecha_cambio DESC LIMIT 1), reparaciones.fecha_entrada)")
        tiempo_promedio = s.execute(_text(f"""
            SELECT AVG(CAST(({_dif_dias.format(a=_ultima)}) AS REAL))
            FROM reparaciones
            WHERE taller_id = :tid AND (estado = 'Terminado' OR estado = 'Entregado')
        """), tp).scalar()

        if tiempo_promedio:
            tiempo_medio_dias = round(float(tiempo_promedio), 1)

    # ========== MÉTRICA 3: REPARACIONES POR TÉCNICO ==========
    # reparaciones_historial lleva taller_id desnormalizado → filtro directo.
    reparaciones_por_tecnico = s.execute(_text("""
        SELECT usuario, COUNT(*) as cantidad
        FROM reparaciones_historial
        WHERE taller_id = :tid AND usuario IS NOT NULL AND usuario != ''
        GROUP BY usuario
        ORDER BY cantidad DESC
    """), tp).all()

    tecnico_dict = [{"nombre": t[0], "cantidad": t[1]} for t in reparaciones_por_tecnico] if reparaciones_por_tecnico else []

    # ========== AUDITORÍA RECIENTE (últimos 10 eventos) ==========
    eventos_auditoria = obtener_auditoria_reciente(limite=10)

    s.close()

    # Calcular IVA en ingresos
    iva_total = round(ingresos_total * 0.21, 2)
    iva_mes = round(ingresos_mes * 0.21, 2)

    _dias = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
    _meses = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']
    _ahora = datetime.now()
    now = f"{_dias[_ahora.weekday()]} {_ahora.day} de {_meses[_ahora.month-1]} de {_ahora.year}, {_ahora.strftime('%H:%M')}"

    return render_template(
        "dashboard.html",
        now=now,
        total_clientes=total_clientes,
        total_reparaciones=total_reparaciones,
        reparaciones_activas=reparaciones_activas,
        reparaciones_terminadas=reparaciones_terminadas,
        porcentaje_activas=porcentaje_activas,
        porcentaje_terminadas=porcentaje_terminadas,
        ingresos_total=round(ingresos_total, 2),
        iva_total=iva_total,
        ingresos_mes=round(ingresos_mes, 2),
        iva_mes=iva_mes,
        reparaciones_mes=reparaciones_mes,
        reparaciones_completadas_mes=reparaciones_completadas_mes,
        ultimas_reparaciones=ultimas_reparaciones,
        dispositivos_top=dispositivos_dict,
        estados_distribucion=estados_dict,
        dinero_cobrado=round(dinero_cobrado, 2),
        dinero_por_cobrar=round(dinero_por_cobrar, 2),
        reparaciones_pendiente_pago=reparaciones_pendiente_pago,
        reparaciones_pagadas=reparaciones_pagadas,
        tasa_cobro=tasa_cobro,
        reparaciones_sin_pagar=reparaciones_sin_pagar_list,
        reparaciones_atrasadas=reparaciones_atrasadas_list,
        ingresos_por_mes=ingresos_por_mes,
        tiempo_medio_dias=tiempo_medio_dias,
        reparaciones_por_tecnico=tecnico_dict,
        eventos_auditoria=eventos_auditoria,
        user_role=session.get('rol')
    )
