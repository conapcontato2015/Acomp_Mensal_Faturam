"""Compatibilidade: a configuração mora em ``faturamento/config.py``."""
from faturamento.config import (  # noqa: F401
    BASE_DIR, Config, TestConfig, _database_url, _normalizar_url, config, configurar,
)
