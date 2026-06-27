"""Presupuestos con aprobación del cliente — constantes y lógica PURA.

El presupuesto vive como un conjunto de campos en `reparaciones` (una reparación
= un presupuesto activo; reenviar lo sobrescribe y reinicia la validez). Este
módulo concentra las constantes de producto y los helpers SIN acceso a BD:
caducidad evaluada EN LECTURA y el importe a cobrar al aprobar.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Validez por defecto del presupuesto (días). Pasados, una caja 'enviado' se
# trata como 'caducado' al leerla (no hay cron en este entorno; ver B4 / informe).
PRESUPUESTO_VALIDEZ_DIAS = 7

# Porcentaje del total que se cobra al APROBAR. 100 = total (decisión de producto
# v1). Una señal (<100) requeriría además rastrear el saldo pendiente y un
# segundo cobro al recoger — fuera de v1 (ver informe / STOP).
PRESUPUESTO_SENAL_PCT = 100

_FMT = "%Y-%m-%d %H:%M:%S"

# Estados en los que el cliente YA respondió (no admiten nuevas acciones).
ESTADOS_RESPONDIDO = {"aprobado", "rechazado", "cambios_solicitados"}


def caduca_en(desde: datetime | None = None,
              dias: int = PRESUPUESTO_VALIDEZ_DIAS) -> str:
    """Fecha límite de validez (string) a partir de `desde` (o ahora)."""
    base = desde or datetime.now()
    return (base + timedelta(days=dias)).strftime(_FMT)


def esta_caducado(caduca_en_str: str | None, ahora: datetime | None = None) -> bool:
    """¿Pasó la fecha de validez? (None/ilegible → no caducado, fail-open hacia
    'no caducado' para no bloquear por un dato corrupto; el estado manda)."""
    if not caduca_en_str:
        return False
    try:
        limite = datetime.strptime(str(caduca_en_str)[:19], _FMT)
    except (ValueError, TypeError):
        return False
    return (ahora or datetime.now()) > limite


def estado_efectivo(estado: str | None, caduca_en_str: str | None,
                    ahora: datetime | None = None) -> str | None:
    """Estado real considerando la caducidad EN LECTURA: si está 'enviado' y
    pasó la validez, devuelve 'caducado'. El resto se devuelve tal cual (un
    presupuesto ya respondido no caduca)."""
    if estado == "enviado" and esta_caducado(caduca_en_str, ahora):
        return "caducado"
    return estado


def puede_responder(estado_efectivo_val: str | None) -> bool:
    """¿El cliente puede aprobar/rechazar/pedir cambios? Solo si sigue 'enviado'
    (ni caducado, ni ya respondido, ni inexistente)."""
    return estado_efectivo_val == "enviado"


def importe_a_cobrar(precio: float | None,
                     pct: int = PRESUPUESTO_SENAL_PCT) -> float:
    """Importe a cobrar al aprobar (total por defecto). 0 si no hay precio."""
    if not precio or precio <= 0:
        return 0.0
    return round(float(precio) * pct / 100.0, 2)
