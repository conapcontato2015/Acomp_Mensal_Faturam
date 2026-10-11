"""Tela de conferência (resumo SEFAZ × sistema contábil) e exportações. [esqueleto — Fase 2]"""
from __future__ import annotations

from flask import render_template_string

from .. import bp
from ..identidade import exigir_usuario


@bp.get("/conferencia")
@exigir_usuario
def conferencia():
    return render_template_string("{% extends 'faturamento/base.html' %}{% block conteudo %}<h1>Conferência</h1>{% endblock %}")
