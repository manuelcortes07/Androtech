"""Capa Stripe de la SUSCRIPCIÓN del SaaS (Fase 3b).

⚠️ FLUJO SEPARADO. Este módulo es la suscripción que YO (la plataforma) cobro a
los talleres. Es DISTINTO del flujo de pago de reparaciones (un taller cobrando
a SUS clientes), que vive en `app.py` (`publico_pagar` + `/stripe/webhook`) y
usa `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET`.

Para que los dos flujos NO se mezclen jamás:
- claves propias: `STRIPE_SAAS_SECRET_KEY`, `STRIPE_SAAS_WEBHOOK_SECRET`,
  `STRIPE_SAAS_PRICE_ID` (un Price recurrente de 24,99 €/mes);
- un `StripeClient` DEDICADO, que NO toca el `stripe.api_key` global que usa el
  flujo de reparaciones;
- endpoint de webhook propio (`/saas/webhook` en app.py), verificado con
  `STRIPE_SAAS_WEBHOOK_SECRET`.

Si en algún punto este flujo y el de reparaciones parecen entrar en conflicto:
PARAR y consultar.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

# Plan único de producto (Fase 3b): 24,99 €/mes, prueba de 14 días con tarjeta
# requerida por adelantado.
TRIAL_DIAS = 14

STRIPE_SAAS_SECRET_KEY = os.environ.get("STRIPE_SAAS_SECRET_KEY", "")
STRIPE_SAAS_WEBHOOK_SECRET = os.environ.get("STRIPE_SAAS_WEBHOOK_SECRET", "")
STRIPE_SAAS_PRICE_ID = os.environ.get("STRIPE_SAAS_PRICE_ID", "")

_FMT = "%Y-%m-%d %H:%M:%S"

_client = None


def _get_client():
    """StripeClient dedicado al SaaS (lazy). Aislado del stripe.api_key global."""
    global _client
    if _client is None:
        import stripe

        _client = stripe.StripeClient(STRIPE_SAAS_SECRET_KEY)
    return _client


def is_configured() -> bool:
    """True si hay clave secreta y price del SaaS (si no, el alta corre sin
    Stripe, útil en dev/tests con mocks)."""
    return bool(STRIPE_SAAS_SECRET_KEY and STRIPE_SAAS_PRICE_ID)


# ─── Operaciones Stripe (todas vía el client dedicado) ──────────────────────
def crear_customer(email: str, nombre: str):
    return _get_client().v1.customers.create({"email": email, "name": nombre})


def crear_checkout_suscripcion(customer_id: str, taller_id: int, success_url: str, cancel_url: str):
    """Checkout en modo subscription: TARJETA REQUERIDA + trial de 14 días.

    La Subscription real se crea cuando el taller completa el Checkout; su id
    llega por webhook (`checkout.session.completed`). El primer cobro es
    automático el día 15 si no cancela.
    """
    return _get_client().v1.checkout.sessions.create(
        {
            "mode": "subscription",
            "customer": customer_id,
            "line_items": [{"price": STRIPE_SAAS_PRICE_ID, "quantity": 1}],
            "subscription_data": {"trial_period_days": TRIAL_DIAS},
            "payment_method_collection": "always",  # tarjeta requerida en el trial
            "success_url": success_url,
            "cancel_url": cancel_url,
            # `flujo` distingue inequívocamente este Checkout del de reparaciones.
            "metadata": {"taller_id": str(taller_id), "flujo": "saas_suscripcion"},
        }
    )


def crear_portal(customer_id: str, return_url: str):
    """Stripe Customer Portal: el admin gestiona tarjeta / cancela suscripción."""
    return _get_client().v1.billing_portal.sessions.create(
        {
            "customer": customer_id,
            "return_url": return_url,
        }
    )


def construir_evento(payload, sig_header):
    """Verifica la firma del webhook del SaaS con STRIPE_SAAS_WEBHOOK_SECRET."""
    import stripe

    return stripe.Webhook.construct_event(payload, sig_header, STRIPE_SAAS_WEBHOOK_SECRET)


# ─── Lógica de estado de suscripción (pura, fácil de testear) ───────────────
def trial_fin_str(ahora: datetime | None = None) -> str:
    """Fecha de fin de trial (ahora + 14 días) en el formato de la BD."""
    ahora = ahora or datetime.now()
    return (ahora + timedelta(days=TRIAL_DIAS)).strftime(_FMT)


def _parse_fecha(valor: str) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        try:
            return datetime.strptime(valor, _FMT)
        except ValueError:
            return None


def acceso_bloqueado(estado: str, trial_fin: str | None, ahora: datetime | None = None) -> bool:
    """True si el taller NO puede acceder (BLOQUEO). Política Fase 3b:

    - 'activo' → acceso.
    - 'trial' dentro de los 14 días → acceso; trial expirado sin pago → BLOQUEO.
    - 'suspendido' / 'cancelado' / cualquier otro → BLOQUEO.

    Bloquear NUNCA borra datos: solo corta el acceso interno.
    """
    ahora = ahora or datetime.now()
    if estado == "activo":
        return False
    if estado == "trial":
        fin = _parse_fecha(trial_fin)
        if fin is None:
            return False  # trial sin fecha → permitir (defensivo, no penalizar)
        return ahora > fin
    return True  # suspendido, cancelado, etc.


def estado_por_status_stripe(status: str) -> str:
    """Mapea el status de la Subscription de Stripe → Taller.estado."""
    return {
        "trialing": "trial",
        "active": "activo",
        "past_due": "suspendido",
        "unpaid": "suspendido",
        "incomplete": "suspendido",
        "incomplete_expired": "suspendido",
        "paused": "suspendido",
        "canceled": "cancelado",
    }.get(status, "suspendido")
