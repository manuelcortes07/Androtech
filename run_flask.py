#!/usr/bin/env python
"""Iniciar Flask sin debug para ver errores claros"""

from app import app

if __name__ == "__main__":
    try:
        print("Iniciando servidor Flask...")
        app.run(debug=False, host='127.0.0.1', port=5000)
    except Exception as e:
        print(f"ERROR al iniciar Flask: {e}")
        import traceback
        traceback.print_exc()
