"""Camada de serviço: TODA regra de negócio fica aqui.

Telas (views) e API só chamam estas funções — assim as regras valem igual nas duas.
"""


class RegraViolada(Exception):
    """Erro de validação/regra de negócio com mensagens para mostrar ao usuário."""

    def __init__(self, mensagens, campo_por_mensagem=None):
        if isinstance(mensagens, str):
            mensagens = [mensagens]
        self.mensagens = list(mensagens)
        self.campos = campo_por_mensagem or {}
        super().__init__("; ".join(self.mensagens))


class SemPermissao(RegraViolada):
    """Ação fora da própria carteira (somente leitura)."""
