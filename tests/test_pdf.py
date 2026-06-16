"""Tests del generador de PDF (utils/pdf_generator.py).

Regresión del bug aparcado (B5): `reparacion_data['id']` puede llegar como str
desde la metadata del webhook de Stripe, y el formato `:05d` reventaba con
"Unknown format code 'd' for object of type 'str'". Ahora se coacciona a int.
"""

from utils.pdf_generator import generar_presupuesto_pdf


def _datos(rep_id):
    return {
        "id": rep_id,
        "dispositivo": "iPhone 12",
        "descripcion": "Pantalla rota",
        "estado": "Terminado",
        "precio": 120.0,
        "fecha_entrada": "2026-01-15",
        "cliente_nombre": "Juan Pérez",
        "cliente_telefono": "600111222",
        "cliente_email": "juan@example.com",
        "cliente_direccion": "Calle Real 1, Huelva",
    }


def _es_pdf(buffer):
    buffer.seek(0)
    data = buffer.read()
    return data[:4] == b"%PDF" and len(data) > 1000


def test_pdf_con_id_string_no_revienta():
    # El caso del webhook: id llega como cadena.
    buf = generar_presupuesto_pdf(_datos("58"), tipo_documento="factura",
                                  base_url="http://localhost")
    assert _es_pdf(buf)


def test_pdf_con_id_int_funciona():
    buf = generar_presupuesto_pdf(_datos(58), tipo_documento="presupuesto",
                                  base_url="http://localhost")
    assert _es_pdf(buf)


def test_pdf_con_id_invalido_cae_a_cero():
    # id no numérico → no revienta, usa 0.
    buf = generar_presupuesto_pdf(_datos("abc"), base_url="http://localhost")
    assert _es_pdf(buf)
