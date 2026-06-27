"""Blueprint de facturación / pagos de reparaciones (refactor B1).

Flujo de pago de UNA reparación: marcar pagada a mano, checkout Stripe público,
página de retorno y el WEBHOOK de Stripe (/stripe/webhook). Es el flujo de pago
de reparaciones (stripe.api_key global) — NO el de la suscripción del SaaS
(ese vive en blueprints/suscripcion.py con su StripeClient dedicado). NUNCA se
mezclan. Comportamiento idéntico al que tenían en app.py; sólo cambia el nombre
de endpoint (stripe_webhook → pagos.stripe_webhook, etc.).

El webhook conserva sus 4 garantías: exención CSRF (_CSRF_EXENTAS en app.py),
firma fail-closed (sin lib stripe → 503), idempotencia (ledger stripe_eventos) y
control de importe (discrepancia → rechazo + auditoría).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import select

try:
    import stripe
except ImportError:
    stripe = None

from audit import registrar_auditoria
from auth import login_required
from branding import taller_branding
from database import get_session, insert_or_ignore
from models import Cliente, Reparacion, StripeEvento
from services import notificador
from utils.pdf_generator import generar_presupuesto_pdf
from utils.security import csrf_protect

logger = logging.getLogger("androtech")

# Claves del flujo de pago de reparaciones (mismas env vars que lee app.py, que
# además configura stripe.api_key global al arrancar).
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")


def _mask_key(key: str) -> str:
    """Enmascara una clave para los logs (nunca el secreto completo)."""
    if not key or len(key) < 8:
        return key
    return key[:4] + "..." + key[-4:]


bp = Blueprint("pagos", __name__)


@bp.route("/reparaciones/<int:id>/marcar-pagado", methods=["POST"])
@login_required
@csrf_protect
def marcar_reparacion_pagada(id):
    """
    Marca una reparación como pagada.
    Solo accesible por admin y técnicos.
    """
    with get_session() as s:
        rep = s.get(Reparacion, id)

        if not rep:
            flash('❌ Reparación no encontrada.', 'danger')
            return redirect(url_for("reparaciones.reparaciones"))

        # Validar que NO esté ya pagada
        if rep.estado_pago == 'Pagado':
            flash('❌ Esta reparación ya está marcada como pagada.', 'warning')
            return redirect(url_for("reparaciones.editar_reparacion", id=id))

        # Validar que tenga precio
        if not rep.precio or rep.precio <= 0:
            flash('❌ No se puede marcar como pagada: sin presupuesto asignado.', 'danger')
            return redirect(url_for("reparaciones.editar_reparacion", id=id))

        # Obtener datos del formulario
        metodo_pago = request.form.get("metodo_pago", "").strip()

        if not metodo_pago:
            flash('❌ Debe seleccionar un método de pago.', 'danger')
            return redirect(url_for("reparaciones.editar_reparacion", id=id))

        # Actualizar BD
        rep.estado_pago = 'Pagado'
        rep.fecha_pago = datetime.now().strftime("%Y-%m-%d")
        rep.metodo_pago = metodo_pago
        s.commit()
    try:
        logger.info(json.dumps({
            "event": "reparacion_pagada",
            "reparacion_id": id,
            "metodo_pago": metodo_pago,
            "usuario": session.get('usuario')
        }, ensure_ascii=False))
    except Exception:
        logger.info(f"reparacion_pagada id={id} metodo={metodo_pago}")

    flash(f'✅ Pago registrado correctamente ({metodo_pago}).', 'success')
    return redirect(url_for("reparaciones.editar_reparacion", id=id))


@bp.route('/publico/pagar/<int:id>', methods=['POST'])
@bp.route('/t/<slug>/publico/pagar/<int:id>', methods=['POST'])
@csrf_protect
def publico_pagar(id, slug=None):
    """Endpoint de pago público. Verificación por email antes de crear sesión Stripe."""
    # Fase 2.4 (riesgo 🔴 #2): el pago opera sobre UNA reparación concreta (id).
    # Resolvemos su taller desde el id y fijamos g.taller_id para que el filtro
    # ORM trabaje en el taller correcto y la metadata de Stripe lo lleve. Así un
    # pago jamás puede cruzar de taller.
    from tenancy import _taller_de_reparacion
    _tid_rep = _taller_de_reparacion(id)
    if _tid_rep:
        g.taller_id = _tid_rep

    # 1. Validar email
    cliente_email = request.form.get('cliente_email', '').strip().lower()
    if not cliente_email or '@' not in cliente_email:
        flash('⚠️ Debes proporcionar un correo válido (ej: cliente@ejemplo.com).', 'danger')
        return redirect(url_for('publico.consulta'))

    try:
        with get_session() as s:
            reparacion = s.execute(
                select(
                    Reparacion.id, Reparacion.precio, Reparacion.estado_pago,
                    Cliente.email.label('cliente_email'),
                    Cliente.nombre.label('cliente_nombre'),
                ).join(Cliente, Cliente.id == Reparacion.cliente_id)
                .where(Reparacion.id == id)
            ).mappings().first()
    except Exception:
        logger.exception(json.dumps({"event": "publico_pagar_lookup_error"}, ensure_ascii=False))
        flash('❌ No se pudo completar la operación. Inténtalo de nuevo.', 'danger')
        return redirect(url_for('publico.consulta'))

    # 2. Validar que reparación existe
    if not reparacion:
        flash(f'❌ Reparación #{id} no encontrada en el sistema.', 'danger')
        return redirect(url_for('publico.consulta'))

    # 3. Validar que NO está ya pagada
    if reparacion['estado_pago'] == 'Pagado':
        flash('✅ Esta reparación ya está pagada. No se puede procesar otro pago.', 'info')
        return redirect(url_for('publico.consulta'))

    # 4. Validar precio existe y es > 0
    try:
        precio = float(reparacion['precio']) if reparacion['precio'] else 0
        if precio <= 0:
            flash('❌ No hay un importe válido a pagar para esta reparación.', 'danger')
            return redirect(url_for('publico.consulta'))
    except (ValueError, TypeError):
        flash('❌ Error: el precio no es válido.', 'danger')
        return redirect(url_for('publico.consulta'))

    # 5. Validar email coincide con cliente registrado
    cliente_email_bd = str(reparacion['cliente_email'] or '').strip().lower()
    if not cliente_email_bd:
        flash('❌ El cliente no tiene email registrado. Contacta con administración.', 'danger')
        return redirect(url_for('publico.consulta'))

    if cliente_email != cliente_email_bd:
        flash('❌ El correo no coincide con el cliente registrado para esta reparación.', 'danger')
        return redirect(url_for('publico.consulta'))

    # 6. Validar Stripe configurado
    if not STRIPE_SECRET_KEY or stripe is None:
        flash('⚠️ El sistema de pagos no está configurado. Contacta con el administrador.', 'danger')
        return redirect(url_for('publico.consulta'))
    # si la clave se ve como pública, advertir al usuario/administrador
    if STRIPE_SECRET_KEY.startswith('pk_'):
        logger.warning('Stripe secret key parece una clave pública (pk_...).')
        flash('❌ Clave secreta de Stripe inválida. Verifica las variables de entorno.', 'danger')
        return redirect(url_for('publico.consulta'))

    # 7. Crear sesión Stripe Checkout
    try:
        amount_cents = int(round(precio * 100))
        # obtener nombre de cliente en variable (sqlite3.Row no tiene .get)
        cliente_nombre = reparacion['cliente_nombre'] if reparacion['cliente_nombre'] else ''
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': f"Reparación #{id} - {cliente_nombre or 'Cliente'}"
                    },
                    'unit_amount': amount_cents,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('pagos.pago_exito', id=id, _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('publico.consulta', _external=True),
            metadata={
                'reparacion_id': str(id),
                'taller_id': str(g.taller_id),  # Fase 2.4: el webhook lo verifica
                'cliente_email': cliente_email,
                'cliente_nombre': cliente_nombre
            }
        )
        try:
            logger.info(json.dumps({
                "event": "checkout_session_created",
                "reparacion_id": id,
                "session_id": getattr(checkout_session, 'id', None),
                "cliente_email": cliente_email
            }, ensure_ascii=False))
        except Exception:
            logger.info(f"checkout_session_created reparacion={id} cliente={cliente_email}")
        return redirect(checkout_session.url, code=303)
    except stripe.error.CardError as e:
        flash(f'❌ Error de tarjeta: {e.user_message}', 'danger')
        return redirect(url_for('publico.consulta'))
    except stripe.error.RateLimitError:
        flash('❌ Demasiadas solicitudes. Intenta de nuevo en unos momentos.', 'danger')
        return redirect(url_for('publico.consulta'))
    except stripe.error.InvalidRequestError as e:
        flash(f'❌ Error en la solicitud: {e.user_message}', 'danger')
        return redirect(url_for('publico.consulta'))
    except stripe.error.AuthenticationError as e:
        # log masked key and error message for admin debugging
        logger.error(
            "Stripe authentication failed when creating checkout session. "
            "api_key=%s message=%s",
            _mask_key(stripe.api_key) if stripe and getattr(stripe, 'api_key', None) else None,
            str(e.user_message or e)
        )
        flash('❌ Error de autenticación con Stripe. Verifica las claves.', 'danger')
        return redirect(url_for('publico.consulta'))
    except stripe.error.APIConnectionError:
        flash('❌ Error de conexión con Stripe. Intenta de nuevo más tarde.', 'danger')
        return redirect(url_for('publico.consulta'))
    except Exception as e:
        flash('❌ No se pudo iniciar el pago. Inténtalo de nuevo.', 'danger')
        logger.exception(json.dumps({
            "event": "publico_pagar_error",
            "error": str(e)
        }, ensure_ascii=False))
        return redirect(url_for('publico.consulta'))


@bp.route('/presupuesto/aprobar', methods=['POST'])
@csrf_protect
def presupuesto_aprobar():
    """El cliente APRUEBA el presupuesto desde el portal → pago Stripe.

    El presupuesto se marca 'aprobado' SÓLO en el webhook (tras confirmación de
    pago real y firma verificada), nunca aquí. resolver_taller ya fijó g.taller_id
    desde el `codigo`, así que el ORM resuelve la reparación del taller correcto;
    la metadata lleva taller_id y el webhook lo re-verifica (no cruza de taller).
    """
    from presupuestos import estado_efectivo, importe_a_cobrar, puede_responder
    codigo = "".join((request.form.get('codigo') or '').split())
    if not codigo:
        flash('Falta el código de seguimiento.', 'danger')
        return redirect(url_for('publico.consulta'))
    with get_session() as s:
        rep = s.execute(
            select(
                Reparacion.id, Reparacion.precio, Reparacion.estado_pago,
                Reparacion.presupuesto_estado, Reparacion.presupuesto_caduca_en,
                Cliente.nombre.label('cliente_nombre'),
                Cliente.email.label('cliente_email'),
            ).join(Cliente, Cliente.id == Reparacion.cliente_id)
            .where(Reparacion.codigo_publico == codigo)
        ).mappings().first()
    if not rep:
        flash('No se encontró el presupuesto.', 'danger')
        return redirect(url_for('publico.consulta'))
    efectivo = estado_efectivo(rep['presupuesto_estado'], rep['presupuesto_caduca_en'])
    if not puede_responder(efectivo):
        flash('Este presupuesto ya no admite respuesta (caducado o ya respondido).',
              'warning')
        return redirect(url_for('publico.consulta', codigo=codigo))
    if rep['estado_pago'] == 'Pagado':
        flash('Esta reparación ya está pagada.', 'info')
        return redirect(url_for('publico.consulta', codigo=codigo))
    importe = importe_a_cobrar(rep['precio'])
    if importe <= 0:
        flash('El importe del presupuesto no es válido.', 'danger')
        return redirect(url_for('publico.consulta', codigo=codigo))
    if not STRIPE_SECRET_KEY or stripe is None or STRIPE_SECRET_KEY.startswith('pk_'):
        flash('El sistema de pagos no está disponible. Contacta con el taller.',
              'danger')
        return redirect(url_for('publico.consulta', codigo=codigo))

    rid = rep['id']
    cliente_nombre = rep['cliente_nombre'] or ''
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {'name': f"Presupuesto reparación #{rid} - {cliente_nombre or 'Cliente'}"},
                    'unit_amount': int(round(importe * 100)),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('pagos.pago_exito', id=rid, _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('publico.consulta', codigo=codigo, _external=True),
            metadata={
                'reparacion_id': str(rid),
                'taller_id': str(g.taller_id),     # el webhook lo verifica
                'cliente_email': rep['cliente_email'] or '',
                'cliente_nombre': cliente_nombre,
                'presupuesto': '1',                # marca: aprobar presupuesto
            },
        )
        return redirect(checkout_session.url, code=303)
    except Exception:
        logger.exception(json.dumps({"event": "presupuesto_aprobar_error",
                                     "reparacion_id": rid}, ensure_ascii=False))
        flash('No se pudo iniciar el pago. Inténtalo de nuevo.', 'danger')
        return redirect(url_for('publico.consulta', codigo=codigo))


@bp.route('/pago_exito')
def pago_exito():
    # Página de éxito (Stripe redirige aquí con session_id)
    session_id = request.args.get('session_id')
    reparacion_id = request.args.get('id')
    return render_template('pago_exito.html', session_id=session_id, reparacion_id=reparacion_id)


@bp.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    """Webhook de Stripe para procesar eventos de pago."""
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')

    # 1. Validar que webhook secret está configurado
    if not STRIPE_WEBHOOK_SECRET:
        logger.error('[WEBHOOK] ❌ Error: STRIPE_WEBHOOK_SECRET no configurado')
        return jsonify({'error': 'Webhook secret not configured'}), 400

    if not sig_header:
        logger.error('[WEBHOOK] ❌ Error: Stripe-Signature header no encontrado')
        return jsonify({'error': 'Missing Stripe-Signature header'}), 400

    # 2. Verificar la FIRMA del evento. FALLA CERRADO (H4): sin la librería
    # `stripe` no se puede verificar la firma → se RECHAZA (igual que el webhook
    # del SaaS). Nunca se procesa un payload sin verificar.
    if not (stripe and hasattr(stripe, 'Webhook')):
        logger.error('[WEBHOOK] ❌ stripe no disponible: no se puede verificar la firma')
        return jsonify({'error': 'Stripe library unavailable; cannot verify signature'}), 503
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        logger.info(f'[WEBHOOK] ✅ Evento válido: {event.get("type")}')
    except Exception as e:
        logger.error(f'[WEBHOOK] ❌ Firma o payload inválido: {str(e)}')
        return jsonify({'error': str(e)}), 400

    # 3. Procesar evento checkout.session.completed
    if event['type'] == 'checkout.session.completed':
        session_obj = event['data']['object']
        metadata = session_obj.get('metadata', {})
        reparacion_id = metadata.get('reparacion_id')
        meta_taller_id = metadata.get('taller_id')
        cliente_email = metadata.get('cliente_email', 'unknown')
        # Si el pago viene de APROBAR un presupuesto, el webhook (única fuente de
        # verdad del pago real) marca además el presupuesto como aprobado.
        es_presupuesto = metadata.get('presupuesto') == '1'
        session_id = session_obj.get('id')

        # Validar metadata
        if not reparacion_id:
            logger.error('[WEBHOOK] ❌ Error: reparacion_id no encontrado en metadata')
            return jsonify({'error': 'Missing reparacion_id in metadata'}), 400

        # Extraer estado/importe reportado por Stripe (si está disponible)
        payment_status = session_obj.get('payment_status') or session_obj.get('status')
        amount_total = None
        # Stripe suele enviar importes en centavos bajo 'amount_total' o 'amount_subtotal'
        if 'amount_total' in session_obj:
            amount_total = session_obj.get('amount_total')
        elif 'amount_subtotal' in session_obj:
            amount_total = session_obj.get('amount_subtotal')

        # Actualizar BD con validaciones adicionales (Fase 1.8: ORM)
        s = None
        try:
            s = get_session()

            # Idempotencia (H6): registra el event_id en el ledger compartido.
            # Si Stripe reenvía el mismo evento, el UNIQUE choca → no se repiten
            # efectos (ni marcar pagado, ni email, ni auditoría duplicada).
            ev_id = event.get('id')
            ins = s.execute(
                insert_or_ignore(StripeEvento)
                .values(event_id=ev_id, tipo=event.get('type'),
                        recibido_en=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                .on_conflict_do_nothing()
            )
            if ev_id and ins.rowcount == 0:
                s.rollback()
                logger.info(json.dumps({"event": "webhook_duplicate",
                                        "stripe_event": ev_id}, ensure_ascii=False))
                return jsonify({'status': 'duplicate'}), 200

            # Verificar que reparación existe
            rep = s.get(Reparacion, reparacion_id)

            if not rep:
                logger.error(json.dumps({
                    "event": "webhook_missing_reparacion",
                    "reparacion_id": reparacion_id,
                    "session_id": session_id
                }, ensure_ascii=False))
                return jsonify({'error': f'Repair #{reparacion_id} not found'}), 404

            # Fase 2.4 (riesgo 🔴 #2): el taller de la metadata DEBE coincidir
            # con el de la reparación. Un pago de un taller jamás puede marcar
            # como pagada una reparación de otro. (El webhook es ruta de
            # plataforma: el ORM no filtra; esta verificación es la barrera.)
            if meta_taller_id is not None and str(rep.taller_id) != str(meta_taller_id):
                logger.error(json.dumps({
                    "event": "webhook_taller_mismatch",
                    "reparacion_id": reparacion_id,
                    "reparacion_taller": rep.taller_id,
                    "metadata_taller": meta_taller_id,
                    "session_id": session_id
                }, ensure_ascii=False))
                return jsonify({'error': 'Taller mismatch'}), 400

            # Verificado: a partir de aquí scopear el resto del webhook al taller
            # de la reparación (auditoría del pago, query email/PDF, slug del QR).
            from tenancy import _slug_por_taller_id
            g.taller_id = rep.taller_id
            g.taller_slug = _slug_por_taller_id(rep.taller_id)

            # Verificar que NO está ya pagada
            if rep.estado_pago == 'Pagado':
                logger.warning(json.dumps({
                    "event": "webhook_already_paid",
                    "reparacion_id": reparacion_id,
                    "session_id": session_id
                }, ensure_ascii=False))
                return jsonify({'status': 'already_paid'}), 200

            # Si Stripe reporta importe y NO coincide con el esperado, NO marcar
            # como pagada (H6): rechaza y deja constancia en audit_log. Un importe
            # distinto del precio del servidor es una anomalía a revisar a mano.
            if amount_total is not None and rep.precio is not None:
                reported = float(amount_total) / 100.0
                expected = float(rep.precio)
                if abs(reported - expected) > 0.01:
                    logger.warning(json.dumps({
                        "event": "webhook_amount_mismatch",
                        "reparacion_id": reparacion_id,
                        "session_id": session_id,
                        "reported_amount": reported,
                        "expected_amount": expected
                    }, ensure_ascii=False))
                    _tid = rep.taller_id
                    s.rollback()
                    registrar_auditoria('pago_importe_no_coincide', None, {
                        'reparacion_id': reparacion_id, 'session_id': session_id,
                        'reported_amount': reported, 'expected_amount': expected,
                    }, ip_address=request.remote_addr, taller_id=_tid)
                    return jsonify({'error': 'Amount mismatch'}), 400

            # Comprobar estado de pago (si está presente)
            if payment_status and str(payment_status).lower() not in ['paid', 'succeeded', 'complete']:
                logger.info(json.dumps({
                    "event": "webhook_payment_not_completed",
                    "reparacion_id": reparacion_id,
                    "session_id": session_id,
                    "payment_status": payment_status
                }, ensure_ascii=False))
                # No marcar como pagada si Stripe no indica pago completado
                return jsonify({'status': 'payment_not_completed'}), 200

            # Marcar como pagada
            rep.estado_pago = 'Pagado'
            rep.fecha_pago = datetime.now().strftime('%Y-%m-%d')
            rep.metodo_pago = 'Tarjeta (Stripe)'
            # Presupuesto aprobado SÓLO aquí (tras confirmación de pago real y
            # verificada la firma): el cliente que aprueba paga y queda autorizado.
            if es_presupuesto:
                rep.presupuesto_estado = 'aprobado'
                rep.presupuesto_respondido_en = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            s.commit()

            # Registrar auditoría y log estructurado
            try:
                registrar_auditoria('pago_registrado', None, {
                    'reparacion_id': reparacion_id,
                    'session_id': session_id,
                    'cliente_email': cliente_email,
                    'amount_reported': amount_total
                }, ip_address=request.remote_addr)
            except Exception:
                logger.exception('Error registrando auditoría de pago')

            # Enviar email de confirmación de pago
            try:
                # Obtener datos completos de la reparación y cliente
                reparacion_data = s.execute(
                    select(
                        Reparacion.__table__,
                        Cliente.nombre, Cliente.email, Cliente.telefono,
                    ).join(Cliente, Reparacion.cliente_id == Cliente.id)
                    # ⚠️ Core → filtro manual; g.taller_id ya es el de la reparación
                    # (fijado tras verificar la metadata más arriba).
                    .where(Reparacion.__table__.c.taller_id == g.taller_id)
                    .where(Reparacion.id == reparacion_id)
                ).mappings().first()

                if reparacion_data:
                    # Generar factura PDF para adjuntar al email
                    pdf_buffer = None
                    try:
                        pdf_reparacion = {
                            'id': reparacion_id,
                            'dispositivo': reparacion_data['dispositivo'],
                            'estado': reparacion_data['estado'],
                            'fecha_entrada': reparacion_data['fecha_entrada'],
                            'precio': reparacion_data['precio'],
                            'descripcion': reparacion_data['descripcion'],
                            'cliente_nombre': reparacion_data['nombre'],
                            'cliente_telefono': reparacion_data['telefono'],
                            'codigo_publico': reparacion_data['codigo_publico'],  # H3
                        }
                        pdf_buffer = generar_presupuesto_pdf(
                            pdf_reparacion, tipo_documento="factura",
                            base_url=request.host_url.rstrip('/'),
                            # El webhook es ruta de plataforma; el slug y los datos
                            # del taller se resuelven desde la metadata de Stripe
                            # (g.taller_id ya es el de la reparación aquí).
                            taller_slug=getattr(g, 'taller_slug', None),
                            taller=taller_branding(),
                        )
                    except Exception:
                        logger.exception(f'[WEBHOOK] Error generando PDF para reparacion {reparacion_id}, se enviara email sin adjunto')

                    # Enviar email de confirmación con factura PDF adjunta
                    notificador.enviar_email("send_payment_confirmation",
                        to_email=reparacion_data['email'],
                        cliente_nombre=reparacion_data['nombre'],
                        reparacion_id=reparacion_id,
                        precio=reparacion_data['precio'],
                        descripcion=reparacion_data['descripcion'],
                        pdf_data=pdf_buffer
                    )
                    logger.info(f'[WEBHOOK] Email de confirmacion enviado a {reparacion_data["email"]} (PDF adjunto: {pdf_buffer is not None})')
                else:
                    logger.warning(f'[WEBHOOK] ⚠️ No se pudieron obtener datos para email de reparación {reparacion_id}')

            except Exception as e:
                logger.exception(f'Error enviando email de confirmación para reparación {reparacion_id}: {str(e)}')

            logger.info(json.dumps({
                "event": "webhook_payment_processed",
                "reparacion_id": reparacion_id,
                "session_id": session_id,
                "cliente_email": cliente_email
            }, ensure_ascii=False))

        except Exception as e:
            logger.error(json.dumps({
                "event": "webhook_update_error",
                "error": str(e),
                "reparacion_id": reparacion_id,
                "session_id": session_id
            }, ensure_ascii=False))
            return jsonify({'error': str(e)}), 500

        finally:
            if s:
                s.close()

    else:
        logger.info(f'[WEBHOOK] ℹ️ Evento no procesado: {event["type"]}')

    return jsonify({'status': 'received'}), 200
