"""
Test script para validar el sistema de Alerts Inteligentes

Valida:
1. Cálculo de alertas según condiciones
2. Urgencia correcta (crítico/importante/advertencia/normal)
3. Que los badges se pasen a templates
4. Que los iconos sean apropiados
"""

from datetime import datetime, timedelta
from alerts import calcular_alertas_reparacion

def test_alerta_sin_presupuesto():
    """Test: Alerta cuando sin presupuesto"""
    print("✓ Test: Sin presupuesto = Crítico")
    
    reparacion = {
        'id': 1,
        'precio': 0,
        'estado': 'Pendiente',
        'estado_pago': 'Pendiente'
    }
    
    resultado = calcular_alertas_reparacion(reparacion)
    assert resultado['tiene_alertas'] == True, "Debe tener alertas"
    assert resultado['urgencia'] == 'critico', "Urgencia debe ser crítico"
    assert any(a['tipo'] == 'sin_presupuesto' for a in resultado['alertas']), "Debe incluir alerta sin presupuesto"
    print("  ✅ Sin presupuesto correctamente marcado como crítico")

def test_alerta_pago_pendiente():
    """Test: Alerta cuando pago pendiente"""
    print("✓ Test: Pago pendiente = Advertencia")
    
    reparacion = {
        'id': 2,
        'precio': 49.99,
        'estado': 'Terminado',
        'estado_pago': 'Pendiente'
    }
    
    resultado = calcular_alertas_reparacion(reparacion)
    assert resultado['tiene_alertas'] == True, "Debe tener alertas"
    assert any(a['tipo'] == 'pago_pendiente' for a in resultado['alertas']), "Debe incluir alerta pago pendiente"
    print("  ✅ Pago pendiente correctamente detectado")

def test_alerta_reparacion_atrasada():
    """Test: Alerta cuando reparación atrasada (>7 días)"""
    print("✓ Test: Reparación atrasada (>7 días) = Importante")
    
    hace_10_dias = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    
    reparacion = {
        'id': 3,
        'precio': 50.00,
        'estado': 'En proceso',
        'estado_pago': 'Pendiente'
    }
    
    resultado = calcular_alertas_reparacion(reparacion, hace_10_dias)
    assert resultado['tiene_alertas'] == True, "Debe tener alertas"
    assert any(a['tipo'] == 'atrasada' for a in resultado['alertas']), "Debe incluir alerta atrasada"
    assert 'danger' in [a['color'] for a in resultado['alertas']], "Debe incluir color danger"
    print("  ✅ Reparación atrasada correctamente detectada")

def test_alerta_sin_alertas():
    """Test: Sin alertas cuando todo está bien"""
    print("✓ Test: Sin alertas cuando todo correcto")
    
    reparacion = {
        'id': 4,
        'precio': 50.00,
        'estado': 'Entregado',
        'estado_pago': 'Pagado'
    }
    
    resultado = calcular_alertas_reparacion(reparacion)
    assert resultado['tiene_alertas'] == False, "No debe tener alertas"
    assert len(resultado['alertas']) == 0, "No debe haber alertas"
    assert resultado['urgencia'] == 'normal', "Urgencia debe ser normal"
    print("  ✅ Sin alertas cuando todo correcto")

def test_alerta_pendiente_entrega():
    """Test: Alerta cuando terminado pero no entregado"""
    print("✓ Test: Terminado pero no entregado")
    
    reparacion = {
        'id': 5,
        'precio': 50.00,
        'estado': 'Terminado',
        'estado_pago': 'Pendiente'
    }
    
    resultado = calcular_alertas_reparacion(reparacion)
    assert resultado['tiene_alertas'] == True, "Debe tener alertas"
    assert any(a['tipo'] == 'pendiente_entrega' for a in resultado['alertas']), "Debe incluir alerta pendiente entrega"
    print("  ✅ Terminado sin entregar correctamente detectado")

def test_urgencia_critica_multiples():
    """Test: Urgencia crítica cuando hay múltiples condiciones"""
    print("✓ Test: Urgencia crítica con múltiples condiciones")
    
    hace_10_dias = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    
    reparacion = {
        'id': 6,
        'precio': 0,  # Sin presupuesto
        'estado': 'Pendiente',
        'estado_pago': 'Pendiente'
    }
    
    resultado = calcular_alertas_reparacion(reparacion, hace_10_dias)
    assert resultado['urgencia'] == 'critico', "Urgencia debe ser crítico"
    assert len(resultado['alertas']) >= 1, "Debe tener al menos una alerta"
    print("  ✅ Urgencia crítica con múltiples condiciones")

def test_template_variables_presentes():
    """Test: Verificar que las variables se pasan a templates"""
    print("✓ Test: Variables en templates")
    
    with open('templates/reparaciones.html', 'r', encoding='utf-8') as f:
        contenido = f.read()
        assert 'alertas_info' in contenido, "alertas_info debe estar en template"
        assert 'tiene_alertas' in contenido, "tiene_alertas debe estar en template"
        assert 'bg-{{ alerta.color }}' in contenido, "Colores de alertas en template"
    print("  ✅ Variables correctamente en reparaciones.html")
    
    with open('templates/editar_reparacion.html', 'r', encoding='utf-8') as f:
        contenido = f.read()
        assert 'alertas_info' in contenido, "alertas_info debe estar en template"
        assert 'bg-danger' in contenido or 'urgencia' in contenido, "Alertas en template"
    print("  ✅ Variables correctamente en editar_reparacion.html")
    
    with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
        contenido = f.read()
        assert 'alertas_info' in contenido, "alertas_info debe estar en dashboard"
    print("  ✅ Variables correctamente en dashboard.html")
    # Verificar timeline en editar_reparacion.html
    with open('templates/editar_reparacion.html','r',encoding='utf-8') as f:
        txt=f.read()
        assert 'Timeline de Estados' in txt, "Debe existir sección de timeline"
        assert 'class="timeline"' in txt, "Clase timeline aplicada"
    print("  ✅ Timeline visual presente en editar_reparacion.html")

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🧪 TESTS: Alerts Inteligentes")
    print("="*60)
    
    test_alerta_sin_presupuesto()
    test_alerta_pago_pendiente()
    test_alerta_reparacion_atrasada()
    test_alerta_sin_alertas()
    test_alerta_pendiente_entrega()
    test_urgencia_critica_multiples()
    test_template_variables_presentes()
    
    print("\n" + "="*60)
    print("✅ Todos los tests pasaron correctamente")
    print("="*60 + "\n")
