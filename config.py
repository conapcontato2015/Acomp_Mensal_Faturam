"""Configuração lida de variáveis de ambiente (ou do arquivo .env).

Nada de caminho fixo no código: tudo que muda entre o PC local e o servidor
fica aqui, controlado por variáveis.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _database_url(dados_dir: Path) -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{(dados_dir / 'faturamento.db').as_posix()}"
    # Provedores costumam entregar "postgres://"; o SQLAlchemy 2 quer o driver explícito.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "troque-esta-chave-no-arquivo-env")
    DADOS_DIR = Path(os.getenv("DADOS_DIR", str(BASE_DIR / "dados")))
    SQLALCHEMY_DATABASE_URI = _database_url(DADOS_DIR)
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # local = janela "Quem está usando?"; plataforma = usuário vem do login da plataforma
    MODO_AUTH = os.getenv("MODO_AUTH", "local")
    AUTH_HEADER = os.getenv("AUTH_HEADER", "X-Remote-User")

    # Prefixo de URL quando o módulo roda dentro de outra aplicação (ex.: /faturamento)
    URL_PREFIX = os.getenv("URL_PREFIX", "")

    BACKUP_DIAS = int(os.getenv("BACKUP_DIAS", "30"))
    LIMITE_VARIACAO = float(os.getenv("LIMITE_VARIACAO", "0.5"))

    # De onde vêm os responsáveis: manual (padrão), planilha, api
    RESPONSAVEIS_PROVEDOR = os.getenv("RESPONSAVEIS_PROVEDOR", "manual")
    RESPONSAVEIS_API_URL = os.getenv("RESPONSAVEIS_API_URL", "")
    RESPONSAVEIS_API_TOKEN = os.getenv("RESPONSAVEIS_API_TOKEN", "")

    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "5000"))

    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # uploads de planilha até 20 MB


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SECRET_KEY = "teste"
    BACKUP_DIAS = 0
    DADOS_DIR = Path(os.getenv("TEST_DADOS_DIR", "/tmp/faturamento-testes"))
