"""Configuração lida de variáveis de ambiente (ou do arquivo .env).

Nada de caminho fixo no código: tudo que muda entre o PC local e o servidor
fica aqui, controlado por variáveis.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _normalizar_url(url: str) -> str:
    """Provedores costumam entregar "postgres://"; o SQLAlchemy 2 quer o driver explícito."""
    url = (url or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _database_url(dados_dir: Path) -> str:
    url = _normalizar_url(os.getenv("DATABASE_URL", ""))
    if not url:
        return f"sqlite:///{(dados_dir / 'faturamento.db').as_posix()}"
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

    # De onde vêm os responsáveis: manual (padrão), api, controle_fiscal
    RESPONSAVEIS_PROVEDOR = os.getenv("RESPONSAVEIS_PROVEDOR", "manual")
    RESPONSAVEIS_API_URL = os.getenv("RESPONSAVEIS_API_URL", "")
    RESPONSAVEIS_API_TOKEN = os.getenv("RESPONSAVEIS_API_TOKEN", "")

    # Controle Fiscal (outro sistema da CONAP, no mesmo PC): lido direto do PostgreSQL dele, SÓ LEITURA.
    # Vazio = integração desligada. Ex.: postgresql://usuario:senha@localhost:5432/controle_fiscal
    FOLHA_DATABASE_URL = _normalizar_url(os.getenv("FOLHA_DATABASE_URL", ""))
    # Nomes de responsável que diferem entre os sistemas: "NomeLa=NomeAqui;Outro=Natan"
    FOLHA_MAPA_RESPONSAVEIS = os.getenv("FOLHA_MAPA_RESPONSAVEIS", "")

    # Cruzamento Domínio × SEFAZ (online, no Manus): números do mês por empresa, SÓ LEITURA.
    # Vazio = integração desligada. A chave é a mesma FATURAMENTO_API_KEY cadastrada no Manus.
    CRUZAMENTO_URL = os.getenv("CRUZAMENTO_URL", "").rstrip("/")
    CRUZAMENTO_API_KEY = os.getenv("CRUZAMENTO_API_KEY", "")
    CRUZAMENTO_TIMEOUT = int(os.getenv("CRUZAMENTO_TIMEOUT", "90"))

    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "5000"))

    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # uploads de planilha até 20 MB

    # Cookie de sessão não vai em POST vindo de outro site (reforça a proteção CSRF)
    SESSION_COOKIE_SAMESITE = "Lax"


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SECRET_KEY = "teste"
    BACKUP_DIAS = 0
    DADOS_DIR = Path(os.getenv("TEST_DADOS_DIR", "/tmp/faturamento-testes"))
    FOLHA_DATABASE_URL = ""
    FOLHA_MAPA_RESPONSAVEIS = ""
    CRUZAMENTO_URL = ""
    CRUZAMENTO_API_KEY = ""
