from app import app


def get_csrf_token(client, path="/"):
    # visit a page to set the session token
    rv = client.get(path)
    with client.session_transaction() as sess:
        return sess.get("csrf_token")


def test_csrf_contacto():
    with app.test_client() as c:
        # posting without token should be blocked
        rv = c.post('/contacto', data={
            'nombre': 'Test',
            'email': 'test@example.com',
            'telefono': '123',
            'tipo': 'Cliente',
            'mensaje': 'hola'
        })
        assert rv.status_code == 400

        token = get_csrf_token(c, '/contacto')
        assert token is not None

        rv = c.post('/contacto', data={
            'nombre': 'Test',
            'email': 'test@example.com',
            'telefono': '123',
            'tipo': 'Cliente',
            'mensaje': 'hola',
            'csrf_token': token
        })
        # should render success page (200)
        assert rv.status_code == 200
        assert b"Muchas gracias" in rv.data or b"contacto_exito" in rv.data


def test_csrf_consulta():
    with app.test_client() as c:
        rv = c.post('/consulta', data={'id_reparacion': '1'})
        assert rv.status_code == 400

        token = get_csrf_token(c, '/consulta')
        assert token is not None

        rv = c.post('/consulta', data={'id_reparacion': '1', 'csrf_token': token})
        assert rv.status_code == 200
        # Even if no record exists, page should load normally
        assert b"No se encontr" in rv.data or b"Reparaci" in rv.data


def test_csrf_publico_pagar():
    with app.test_client() as c:
        # we need a token before posting
        token = get_csrf_token(c, '/consulta')
        assert token is not None

        rv = c.post('/publico/pagar/1', data={'cliente_email': 'test@example.com'})
        assert rv.status_code == 400

        rv = c.post('/publico/pagar/1', data={'cliente_email': 'test@example.com', 'csrf_token': token})
        # with token the status should not be 400; could be 302 or 200 depending on validations
        assert rv.status_code != 400
