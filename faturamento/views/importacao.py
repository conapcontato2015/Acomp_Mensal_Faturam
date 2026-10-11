"""Importação da planilha antiga e da planilha de responsáveis. [esqueleto — Fases 2 e 3]"""
from __future__ import annotations

from flask import render_template_string

from .. import bp
from ..identidade import exigir_usuario


@bp.get("/importacao")
@exigir_usuario
def importacao():
    return render_template_string("{% extends 'faturamento/base.html' %}{% block conteudo %}<h1>Importar planilha</h1>{% endblock %}")


@bp.get("/empresas/importar-responsaveis")
@exigir_usuario
def importar_responsaveis():
    return render_template_string("{% extends 'faturamento/base.html' %}{% block conteudo %}<h1>Importar responsáveis</h1>{% endblock %}")
