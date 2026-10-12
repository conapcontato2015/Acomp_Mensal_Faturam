"""Entrada WSGI para servidor (gunicorn/waitress): ``gunicorn wsgi:app``.

Aplica as migrações e semeia o banco ao subir.
"""
from app import create_app
from faturamento.bootstrap import preparar_banco

app = create_app()
preparar_banco(app)
