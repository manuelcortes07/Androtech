from app import app


def test_export_access_control():
    with app.test_client() as c:
        # not logged in -> redirect to login
        rv = c.get('/export/reparaciones')
        assert rv.status_code == 302

        # logged in as unauthorized role
        with c.session_transaction() as sess:
            sess['usuario'] = 'u'
            sess['rol'] = 'tecnico'
        rv = c.get('/export/reparaciones', follow_redirects=True)
        assert b'No tienes permisos' in rv.data or b'permiso' in rv.data

        # logged in as admin -> should return CSV
        with c.session_transaction() as sess:
            sess['usuario'] = 'admin'
            sess['rol'] = 'admin'
        rv = c.get('/export/reparaciones')
        assert rv.status_code == 200
        assert rv.headers.get('Content-Type', '').startswith('text/csv')
        assert b'ID' in rv.data and b'Cliente' in rv.data


if __name__ == '__main__':
    test_export_access_control()
    print('✅ export tests passed')
