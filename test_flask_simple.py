#!/usr/bin/env python
"""Test simple de Flask para diagnóstico"""

from flask import Flask

app = Flask(__name__)

@app.route("/health")
def health():
    return {"status": "ok"}, 200

@app.route("/pdf/test")
def pdf_test():
    return "PDF endpoint funciona", 200

if __name__ == "__main__":
    print("Iniciando servidor de prueba...")
    app.run(debug=True, port=5000)
