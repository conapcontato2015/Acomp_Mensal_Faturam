"""Tabelas do módulo de faturamento.

Todas com prefixo ``fat_`` para conviver com outros subsistemas no mesmo banco.
Valores monetários em NUMERIC(15,2) — nunca float.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, select,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db
from .util import agora as _agora_local

ENTRADA = "E"
SAIDA = "S"
OUTROS = "O"  # não é entrada nem saída: fica fora dos totais de entradas/saídas e do gráfico (ex.: recebimento de caixa)

# sentido -> (nome no singular, título do bloco, nome nos subtotais)
SENTIDOS = {
    ENTRADA: ("Entrada", "ENTRADAS", "entradas"),
    SAIDA: ("Saída", "SAÍDAS", "saídas"),
    OUTROS: ("Outros", "OUTROS", "outros"),
}
ORDEM_SENTIDOS = (ENTRADA, SAIDA, OUTROS)

ORIGEM_MANUAL = "manual"
ORIGEM_PLANILHA = "planilha"
ORIGEM_INTEGRACAO = "integracao"

GRUPO_AUTOR = "AUTOR"
GRUPO_CANC = "CANC"

STATUS_PENDENTE = "pendente"
STATUS_SEM_MOVIMENTO = "sem_movimento"
STATUS_PREENCHIDO = "preenchido"

MOTIVO_PADRAO_AJUSTE = "Arquivos a mais, ausentes no relatório da SEFAZ"
# Ajuste sugerido pelo cruzamento Domínio × SEFAZ (notas do Domínio que faltam no relatório).
# Motivo próprio para reimportar sem mexer nos ajustes digitados à mão.
MOTIVO_CRUZAMENTO = "Arquivos a mais, ausentes no relatório da SEFAZ (cruzamento)"
MOTIVOS_AJUSTE = [
    MOTIVO_PADRAO_AJUSTE,
    "Arquivos no relatório da SEFAZ que a empresa não enviou",
    "Importado da planilha",
    "Outro",
]


def agora() -> datetime:
    return _agora_local()  # hora de Fortaleza, não a do sistema operacional


class Usuario(db.Model):
    __tablename__ = "fat_usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Preenchido quando o usuário for ligado ao login da plataforma.
    external_id: Mapped[str | None] = mapped_column(String(120), unique=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Usuario {self.nome}>"


class TipoDocumento(db.Model):
    __tablename__ = "fat_tipo_documento"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nome: Mapped[str] = mapped_column(String(60), unique=True)
    modelo: Mapped[str] = mapped_column(String(20))
    sentido: Mapped[str] = mapped_column(String(1))  # E | S | O
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def sentido_nome(self) -> str:
        return SENTIDOS.get(self.sentido, SENTIDOS[SAIDA])[0]


fat_empresa_tipo = db.Table(
    "fat_empresa_tipo",
    db.Column("empresa_id", ForeignKey("fat_empresa.id", ondelete="CASCADE"), primary_key=True),
    db.Column("tipo_id", ForeignKey("fat_tipo_documento.id", ondelete="CASCADE"), primary_key=True),
)


class Empresa(db.Model):
    __tablename__ = "fat_empresa"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(160), unique=True)
    cnpj: Mapped[str | None] = mapped_column(String(14), unique=True)  # só dígitos
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    external_id: Mapped[str | None] = mapped_column(String(120), unique=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    tipos: Mapped[list[TipoDocumento]] = relationship(
        secondary=fat_empresa_tipo, order_by="TipoDocumento.ordem", lazy="selectin"
    )
    historico_responsaveis: Mapped[list["EmpresaResponsavel"]] = relationship(
        back_populates="empresa", order_by="EmpresaResponsavel.inicio.desc(), EmpresaResponsavel.id.desc()",
        cascade="all, delete-orphan",
    )

    @property
    def cnpj_formatado(self) -> str:
        c = self.cnpj or ""
        if len(c) != 14:
            return c
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"

    def responsavel_em(self, competencia: date) -> "EmpresaResponsavel | None":
        """Vínculo de carteira vigente na competência (o de início mais recente <= competência)."""
        for vinc in self.historico_responsaveis:  # já ordenado do mais novo para o mais antigo
            if vinc.inicio <= competencia:
                return vinc
        return None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Empresa {self.nome}>"


class EmpresaResponsavel(db.Model):
    """Histórico da carteira: quem responde pela empresa a partir de qual competência."""

    __tablename__ = "fat_empresa_responsavel"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("fat_empresa.id", ondelete="CASCADE"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("fat_usuario.id"))
    inicio: Mapped[date] = mapped_column(Date)  # dia 1 da competência
    origem: Mapped[str] = mapped_column(String(20), default=ORIGEM_MANUAL)
    registrado_por_id: Mapped[int | None] = mapped_column(ForeignKey("fat_usuario.id"))
    registrado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    empresa: Mapped[Empresa] = relationship(back_populates="historico_responsaveis")
    usuario: Mapped[Usuario] = relationship(foreign_keys=[usuario_id], lazy="joined")
    registrado_por: Mapped[Usuario | None] = relationship(foreign_keys=[registrado_por_id])


class Importacao(db.Model):
    __tablename__ = "fat_importacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    arquivo: Mapped[str] = mapped_column(String(255))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("fat_usuario.id"))
    responsavel_id: Mapped[int | None] = mapped_column(ForeignKey("fat_usuario.id"))
    data: Mapped[datetime] = mapped_column(DateTime, default=agora)
    resumo: Mapped[str | None] = mapped_column(Text)  # JSON com contagens e avisos
    desfeita: Mapped[bool] = mapped_column(Boolean, default=False)

    usuario: Mapped[Usuario | None] = relationship(foreign_keys=[usuario_id])
    responsavel: Mapped[Usuario | None] = relationship(foreign_keys=[responsavel_id])


class FonteVersao(db.Model):
    """Versão dos números de uma fonte externa (hoje o cruzamento Domínio × SEFAZ) para empresa + competência.

    Gravada a cada importação aplicada: guarda o que veio de lá (JSON) para comparar com a próxima
    leitura ("mudou lá desde a última importação?") sem depender do que foi digitado aqui.
    """

    __tablename__ = "fat_fonte_versao"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("fat_empresa.id", ondelete="CASCADE"), index=True)
    competencia: Mapped[date] = mapped_column(Date, index=True)
    fonte: Mapped[str] = mapped_column(String(30))
    obtida_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("fat_usuario.id"))
    importacao_id: Mapped[int | None] = mapped_column(ForeignKey("fat_importacao.id", ondelete="SET NULL"))
    assinatura: Mapped[str] = mapped_column(String(64))
    dados: Mapped[str] = mapped_column(Text)  # JSON da empresa como veio da fonte

    usuario: Mapped[Usuario | None] = relationship()
    importacao: Mapped[Importacao | None] = relationship()


class Lancamento(db.Model):
    """Números brutos do relatório da SEFAZ para (empresa, competência, tipo).

    Totais com ajuste NÃO são gravados: saem de ``total_*`` (soma dos ajustes).
    """

    __tablename__ = "fat_lancamento"
    __table_args__ = (UniqueConstraint("empresa_id", "competencia", "tipo_id", name="uq_fat_lancamento_chave"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("fat_empresa.id", ondelete="CASCADE"), index=True)
    competencia: Mapped[date] = mapped_column(Date, index=True)
    tipo_id: Mapped[int] = mapped_column(ForeignKey("fat_tipo_documento.id"))

    qtde_autor: Mapped[int | None] = mapped_column(Integer)
    valor_autor: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    qtde_canc: Mapped[int | None] = mapped_column(Integer)
    valor_canc: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))

    responsavel_id: Mapped[int | None] = mapped_column(ForeignKey("fat_usuario.id"))

    bateu: Mapped[bool] = mapped_column(Boolean, default=False)
    bateu_por_id: Mapped[int | None] = mapped_column(ForeignKey("fat_usuario.id"))
    bateu_em: Mapped[datetime | None] = mapped_column(DateTime)

    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("fat_usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    alterado_por_id: Mapped[int | None] = mapped_column(ForeignKey("fat_usuario.id"))
    alterado_em: Mapped[datetime | None] = mapped_column(DateTime)

    importacao_id: Mapped[int | None] = mapped_column(ForeignKey("fat_importacao.id", ondelete="SET NULL"))

    empresa: Mapped[Empresa] = relationship(lazy="joined")
    tipo: Mapped[TipoDocumento] = relationship(lazy="joined")
    ajustes: Mapped[list["Ajuste"]] = relationship(
        back_populates="lancamento", cascade="all, delete-orphan", order_by="Ajuste.id", lazy="selectin"
    )
    responsavel: Mapped[Usuario | None] = relationship(foreign_keys=[responsavel_id])
    bateu_por: Mapped[Usuario | None] = relationship(foreign_keys=[bateu_por_id])

    def _soma_ajustes(self, grupo: str, campo: str):
        return sum((getattr(a, campo) or 0) for a in self.ajustes if a.grupo == grupo)

    @property
    def ajuste_qtde_autor(self) -> int:
        return int(self._soma_ajustes(GRUPO_AUTOR, "qtde"))

    @property
    def ajuste_valor_autor(self) -> Decimal:
        return Decimal(self._soma_ajustes(GRUPO_AUTOR, "valor"))

    @property
    def ajuste_qtde_canc(self) -> int:
        return int(self._soma_ajustes(GRUPO_CANC, "qtde"))

    @property
    def ajuste_valor_canc(self) -> Decimal:
        return Decimal(self._soma_ajustes(GRUPO_CANC, "valor"))

    @property
    def total_qtde_autor(self) -> int:
        return (self.qtde_autor or 0) + self.ajuste_qtde_autor

    @property
    def total_valor_autor(self) -> Decimal:
        return Decimal(self.valor_autor or 0) + self.ajuste_valor_autor

    @property
    def total_qtde_canc(self) -> int:
        return (self.qtde_canc or 0) + self.ajuste_qtde_canc

    @property
    def total_valor_canc(self) -> Decimal:
        return Decimal(self.valor_canc or 0) + self.ajuste_valor_canc

    @property
    def tem_ajuste(self) -> bool:
        return bool(self.ajustes)

    @property
    def tem_movimento(self) -> bool:
        """Qualquer número diferente de zero (inclui ajustes e cancelamentos)."""
        return any([
            self.total_qtde_autor, self.total_valor_autor,
            self.total_qtde_canc, self.total_valor_canc,
        ])


class Ajuste(db.Model):
    __tablename__ = "fat_ajuste"

    id: Mapped[int] = mapped_column(primary_key=True)
    lancamento_id: Mapped[int] = mapped_column(ForeignKey("fat_lancamento.id", ondelete="CASCADE"), index=True)
    grupo: Mapped[str] = mapped_column(String(5))  # AUTOR | CANC
    qtde: Mapped[int] = mapped_column(Integer, default=0)
    valor: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    motivo: Mapped[str] = mapped_column(String(160))
    observacao: Mapped[str | None] = mapped_column(Text)
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("fat_usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    lancamento: Mapped[Lancamento] = relationship(back_populates="ajustes")
    criado_por: Mapped[Usuario | None] = relationship(lazy="joined")


class Fechamento(db.Model):
    """Marca explícita do mês por empresa. Hoje só registra 'sem movimento'.

    'Preenchido' e 'pendente' são deduzidos dos lançamentos.
    """

    __tablename__ = "fat_fechamento"
    __table_args__ = (UniqueConstraint("empresa_id", "competencia", name="uq_fat_fechamento_chave"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("fat_empresa.id", ondelete="CASCADE"))
    competencia: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    observacao: Mapped[str | None] = mapped_column(Text)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("fat_usuario.id"))
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=agora, onupdate=agora)


class Auditoria(db.Model):
    __tablename__ = "fat_auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    tabela: Mapped[str] = mapped_column(String(40), index=True)
    registro_id: Mapped[int | None] = mapped_column(Integer)
    empresa_id: Mapped[int | None] = mapped_column(Integer, index=True)
    acao: Mapped[str] = mapped_column(String(40))
    descricao: Mapped[str | None] = mapped_column(Text)
    antes: Mapped[str | None] = mapped_column(Text)
    depois: Mapped[str | None] = mapped_column(Text)
    usuario_id: Mapped[int | None] = mapped_column(Integer)
    usuario_nome: Mapped[str | None] = mapped_column(String(80))
    data: Mapped[datetime] = mapped_column(DateTime, default=agora, index=True)


def get_or_404_none(model, pk):
    return db.session.get(model, pk)


__all__ = [
    "Usuario", "TipoDocumento", "Empresa", "EmpresaResponsavel", "Lancamento", "Ajuste",
    "Fechamento", "Auditoria", "Importacao", "FonteVersao", "fat_empresa_tipo", "select",
]
