"""Blueprints de Kintsu (refactor B1).

Cada dominio (auth, publico, reparaciones, clientes, …) vive en su módulo y
expone un `Blueprint`. `app.py` los registra en la app. Durante la migración
gradual conviven rutas ya migradas (aquí) y rutas aún en `app.py`.
"""
