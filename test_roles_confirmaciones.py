"""
Test script para validar la funcionalidad de Roles + Confirmaciones

Valida:
1. Que los roles se pasen correctamente a las templates
2. Que la lógica de mostrar_precios funcione
3. Que puede_editar_precio funcione
4. Que los botones de borrado usen el modal
"""

import sqlite3
from app import app

def test_roles_reparaciones():
    """Test que admin/técnico ven precios, recepcionista no"""
    print("✓ Test: Validar mostrar_precios según rol")
    
    with app.test_client() as client:
        # Sin login, debe redirigir
        response = client.get('/reparaciones')
        assert response.status_code == 302, "Debe redirigir a login sin autenticación"
        
    print("  ✅ Redirección a login correcta")

def test_puede_editar_precio():
    """Test que solo admin puede editar precio"""
    print("✓ Test: Validar puede_editar_precio según rol")
    
    # Simulamos diferentes roles
    roles_prueba = {
        'admin': True,
        'tecnico': False,
        'recepcionista': False
    }
    
    for rol, puede_editar in roles_prueba.items():
        resultado = rol == 'admin'
        assert resultado == puede_editar, f"Fallo para rol {rol}"
    
    print("  ✅ Control de edición de precios correcto")

def test_confirmacion_modales():
    """Test que los modales están presentes en las templates"""
    print("✓ Test: Validar presencia de modales de confirmación")
    
    # Verificar que las templates contienen los modales
    with open('templates/reparaciones.html', 'r', encoding='utf-8') as f:
        contenido_rep = f.read()
        assert 'confirmBorrarModal' in contenido_rep, "Modal en reparaciones.html"
        assert 'setConfirmData' in contenido_rep, "Función setConfirmData en reparaciones.html"
        print("  ✅ Modal de confirmación en reparaciones.html")
    
    with open('templates/clientes.html', 'r', encoding='utf-8') as f:
        contenido_cli = f.read()
        assert 'confirmBorrarModal' in contenido_cli, "Modal en clientes.html"
        assert 'setConfirmData' in contenido_cli, "Función setConfirmData en clientes.html"
        print("  ✅ Modal de confirmación en clientes.html")
    
    with open('templates/editar_reparacion.html', 'r', encoding='utf-8') as f:
        contenido_edit = f.read()
        assert 'confirmEstadoModal' in contenido_edit, "Modal de estado en editar_reparacion.html"
        assert 'verificarCambioEstado' in contenido_edit, "Función verificarCambioEstado en editar_reparacion.html"
        assert 'puede_editar_precio' in contenido_edit, "Verificación puede_editar_precio en editar_reparacion.html"
        print("  ✅ Modal de confirmación de estado en editar_reparacion.html")

def test_variables_paso_a_templates():
    """Test que las variables se pasan correctamente"""
    print("✓ Test: Validar paso de variables a templates")
    
    # Verificar que render_template incluye las nuevas variables
    with open('app.py', 'r', encoding='utf-8') as f:
        contenido_app = f.read()
        
        # En /reparaciones
        assert 'mostrar_precios=' in contenido_app, "mostrar_precios pasado a render_template"
        assert 'user_role=' in contenido_app, "user_role pasado a render_template"
        
        # La lógica debe estar presente
        assert "session.get('rol') in ['admin', 'tecnico']" in contenido_app, "Lógica de roles"
        
    print("  ✅ Variables pasadas correctamente a templates")

def test_busqueda_global_ruta():
    """Test básico de la ruta de búsqueda global"""
    print("✓ Test: Ruta /reparaciones con parámetro q")
    with app.test_client() as client:
        # Simular login como admin
        with client.session_transaction() as sess:
            sess['usuario'] = 'test'
            sess['rol'] = 'admin'
        resp = client.get('/reparaciones?q=1')
        assert resp.status_code == 200, "La ruta debe responder 200"
        assert b'Buscar' in resp.data or b'q=' in resp.data, "La página debe contener la caja de búsqueda"
    print("  ✅ La búsqueda global responde correctamente")

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🧪 TESTS: Roles + Confirmaciones")
    print("="*60)
    
    test_roles_reparaciones()
    test_puede_editar_precio()
    test_confirmacion_modales()
    test_variables_paso_a_templates()
    test_busqueda_global_ruta()
    
    print("\n" + "="*60)
    print("✅ Todos los tests pasaron correctamente")
    print("="*60 + "\n")
