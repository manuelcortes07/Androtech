from app import app

with app.test_client() as c:
    rv = c.get('/reparaciones')
    print('GET /reparaciones ->', rv.status_code)
    data = rv.data.decode('utf-8')
    print(data[:400])
