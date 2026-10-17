"""Compatibilidade: o banco agora é SQLAlchemy puro, em ``faturamento/db.py``."""
from .db import CONVENCAO as convencao  # noqa: F401
from .db import db  # noqa: F401
