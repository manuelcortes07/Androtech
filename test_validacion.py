"""Pruebas unitarias para funciones de validación centralizadas."""

from utils.security import validar_precio


def test_validar_precio_ok():
    assert validar_precio("10")
    assert validar_precio("0.01")
    assert validar_precio("1000.5")
    assert validar_precio(5)  # accepts numeric too


def test_validar_precio_fail():
    assert not validar_precio(0)
    assert not validar_precio(-5)
    assert not validar_precio("-3")
    assert not validar_precio("abc")
    assert not validar_precio("")
    assert not validar_precio(None)


if __name__ == '__main__':
    print("🧪 TESTS: validación precio")
    test_validar_precio_ok()
    test_validar_precio_fail()
    print("✅ Todas las pruebas de validación pasaron")
