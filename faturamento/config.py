"""Configuração do sistema, lida de variáveis de ambiente (ou do arquivo .env na raiz).

Nada de caminho fixo no código: tudo que muda entre o PC local, o servidor e o Conap Ferramentas
fica aqui, controlado por variáveis.

- ``Config`` / ``TestConfig``: valores padrão (classe).
- ``config``: a configuração **ativa**, usada pelas regras (``config["DADOS_DIR"]``). Quem inicia o
  sistema chama ``configurar(Config)`` (ou ``TestConfig`` nos testes).
"""
from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
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


def _bool(nome: str, padrao: bool) -> bool:
    v = os.getenv(nome)
    if v is None or v.strip() == "":
        return padrao
    return v.strip().lower() in ("1", "true", "sim", "s", "yes")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "troque-esta-chave-no-arquivo-env")
    DADOS_DIR = Path(os.getenv("DADOS_DIR", str(BASE_DIR / "dados")))
    SQLALCHEMY_DATABASE_URI = _database_url(DADOS_DIR)

    # local = janela "Quem está usando?"; plataforma = usuário vem do login do Conap Ferramentas (JWT)
    MODO_AUTH = os.getenv("MODO_AUTH", "local")
    # Modo plataforma — de onde vem o usuário logado:
    #   JWT num cookie (padrão do Conap Ferramentas) ou no cabeçalho "Authorization: Bearer";
    #   ou, atrás de um proxy que já validou o login, um cabeçalho com o nome (AUTH_HEADER).
    JWT_COOKIE = os.getenv("JWT_COOKIE", "token")
    JWT_ALGORITMO = os.getenv("JWT_ALGORITMO", "HS256")
    JWT_SEGREDO = os.getenv("JWT_SEGREDO", "")            # HS256: o mesmo segredo do FastAPI da plataforma
    JWT_CHAVE_PUBLICA = os.getenv("JWT_CHAVE_PUBLICA", "")  # RS256/ES256: chave pública (PEM)
    JWT_CAMPO_ID = os.getenv("JWT_CAMPO_ID", "sub")       # campo do token com o id do usuário
    JWT_CAMPO_NOME = os.getenv("JWT_CAMPO_NOME", "nome")  # campo do token com o nome
    JWT_CRIAR_USUARIO = _bool("JWT_CRIAR_USUARIO", True)  # usuário novo no token vira usuário aqui
    AUTH_HEADER = os.getenv("AUTH_HEADER", "X-Remote-User")  # usado só se não houver JWT configurado

    # Prefixo de URL quando o módulo roda dentro de outra aplicação (ex.: /faturamento) — telas antigas
    URL_PREFIX = os.getenv("URL_PREFIX", "")

    BACKUP_DIAS = int(os.getenv("BACKUP_DIAS", "30"))
    LIMITE_VARIACAO = float(os.getenv("LIMITE_VARIACAO", "0.5"))

    # De onde vêm os responsáveis: manual (padrão), api, controle_fiscal
    RESPONSAVEIS_PROVEDOR = os.getenv("RESPONSAVEIS_PROVEDOR", "manual")
    RESPONSAVEIS_API_URL = os.getenv("RESPONSAVEIS_API_URL", "")
    RESPONSAVEIS_API_TOKEN = os.getenv("RESPONSAVEIS_API_TOKEN", "")

    # De onde vem o cadastro de empresas: local (cadastrado aqui, padrão) ou plataforma
    # (cadastro geral do Conap Ferramentas, só leitura — ver faturamento/fontes/empresas.py).
    EMPRESAS_FONTE = os.getenv("EMPRESAS_FONTE", "local")
    PLATAFORMA_DATABASE_URL = _normalizar_url(os.getenv("PLATAFORMA_DATABASE_URL", ""))
    PLATAFORMA_EMPRESAS_TABELA = os.getenv("PLATAFORMA_EMPRESAS_TABELA", "empresas")
    # campo aqui=coluna lá, separados por ";" (só os que diferem do padrão id/nome/cnpj/ativa)
    PLATAFORMA_EMPRESAS_COLUNAS = os.getenv("PLATAFORMA_EMPRESAS_COLUNAS", "")

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
    MODO_AUTH = "local"
    JWT_SEGREDO = ""
    JWT_CHAVE_PUBLICA = ""
    EMPRESAS_FONTE = "local"
    PLATAFORMA_DATABASE_URL = ""
    FOLHA_DATABASE_URL = ""
    FOLHA_MAPA_RESPONSAVEIS = ""
    CRUZAMENTO_URL = ""
    CRUZAMENTO_API_KEY = ""
    RESPONSAVEIS_PROVEDOR = "manual"


def valores_de(obj) -> dict:
    """Atributos em MAIÚSCULAS de uma classe/objeto de configuração (ou um dict)."""
    if isinstance(obj, dict):
        return {k: v for k, v in obj.items() if k.isupper()}
    return {k: getattr(obj, k) for k in dir(obj) if k.isupper()}


class _ConfigAtiva(MutableMapping):
    """Configuração em uso. Começa com ``Config``.

    ``configurar(obj)`` troca tudo de uma vez; ``vincular(mapa)`` passa a ler direto de outro dicionário
    (ex.: ``app.config`` do Flask), para que mudanças feitas nele valham na hora.
    """

    def __init__(self) -> None:
        self._fonte: MutableMapping = {}

    def configurar(self, obj) -> "_ConfigAtiva":
        self._fonte = dict(valores_de(obj))
        return self

    def vincular(self, mapa: MutableMapping) -> "_ConfigAtiva":
        self._fonte = mapa
        return self

    def __getitem__(self, chave):
        return self._fonte[chave]

    def __setitem__(self, chave, valor) -> None:
        self._fonte[chave] = valor

    def __delitem__(self, chave) -> None:
        del self._fonte[chave]

    def __iter__(self):
        return iter(self._fonte)

    def __len__(self) -> int:
        return len(self._fonte)


config = _ConfigAtiva().configurar(Config)


def configurar(obj, **extra) -> _ConfigAtiva:
    """Ativa a configuração ``obj`` (classe, objeto ou dict) e liga o banco nela."""
    from .db import db

    config.configurar(obj)
    config.update(extra)
    db.configurar(config["SQLALCHEMY_DATABASE_URI"])
    return config
