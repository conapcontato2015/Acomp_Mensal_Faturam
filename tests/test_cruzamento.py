"""Importação dos números do mês a partir do cruzamento Domínio × SEFAZ.

O cruzamento (sistema online no Manus) é simulado por um servidor HTTP local que responde como a rota
tRPC ``faturamento.resumoMensal`` (envelope ``{"result":{"data":{"json": ...}}}``).
"""
from __future__ import annotations

import json
import threading
import urllib.parse
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from sqlalchemy import select

from faturamento.models import GRUPO_AUTOR, MOTIVO_CRUZAMENTO, MOTIVO_PADRAO_AJUSTE, FonteVersao
from faturamento.services import cruzamento as svc
from faturamento.services import importacao as svc_imp
from faturamento.services import lancamentos as svc_lanc
from faturamento.util import competencia


CHAVE = "chave-de-teste-123456"
COMP = competencia("2026-08")
CNPJ_A = "12345678000190"
CNPJ_B = "98765432000110"


def tipo(nome, aut=(0, "0.00"), canc=(0, "0.00"), falta=None, sefaz=True, dominio=True, notas=None):
    falta = falta or (0, "0.00")
    return {
        "tipo": nome, "sefazImportado": sefaz, "dominioImportado": dominio,
        "autorizadas": {"qtde": aut[0], "valor": aut[1]}, "canceladas": {"qtde": canc[0], "valor": canc[1]},
        "outrasSemEfeito": 0, "registrosNoMes": aut[0] + canc[0],
        "faltaSefaz": {"qtde": falta[0], "valor": falta[1], "notas": notas or [], "notasOmitidas": 0,
                       "notasDominioNoMes": 10},
    }


def empresa_la(cnpj, nome, *tipos_):
    return {"empresaId": 1, "cnpj": cnpj, "razaoSocial": nome, "nomeFantasia": None, "tipos": list(tipos_),
            "importacoes": [{"id": 41, "tipo": "NFCE_AUTORIZADA", "nomeArquivo": "nfce.xls",
                             "periodoInicio": "01/08/2026", "periodoFim": "31/08/2026", "criadoEm": "2026-09-02T10:00:00Z"}]}


def resposta(*empresas, comp="2026-08"):
    return {"versao": 1, "competencia": comp, "geradoEm": "2026-09-05T12:00:00.000Z", "empresas": list(empresas)}


@pytest.fixture()
def servidor(app):
    """Servidor falso do cruzamento. servidor.dados = resposta(...); servidor.status = 200; servidor.pedidos = [...]"""

    class Estado:
        dados = resposta()
        status = 200
        pedidos: list[dict] = []

    estado = Estado()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silencioso
            pass

        def do_GET(self):  # noqa: N802
            url = urllib.parse.urlparse(self.path)
            entrada = json.loads(urllib.parse.parse_qs(url.query)["input"][0])["json"]
            estado.pedidos.append({"path": url.path, "input": entrada, "auth": self.headers.get("Authorization"),
                                   "ua": self.headers.get("User-Agent")})
            if url.path != "/api/trpc/faturamento.resumoMensal":
                self.send_response(404)
                self.end_headers()
                return
            if self.headers.get("Authorization") != f"Bearer {CHAVE}":
                corpo = {"error": {"json": {"message": "Chave de acesso do Faturamento inválida.",
                                            "data": {"code": "UNAUTHORIZED", "httpStatus": 401}}}}
                status = 401
            elif estado.status != 200:
                corpo = {"error": {"json": {"message": "Banco de dados indisponível"}}}
                status = estado.status
            else:
                dados = dict(estado.dados)
                if entrada.get("cnpj"):
                    dados["empresas"] = [e for e in dados["empresas"] if e["cnpj"] == entrada["cnpj"]]
                corpo, status = {"result": {"data": {"json": dados}}}, 200
            b = json.dumps(corpo).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    app.config.update(CRUZAMENTO_URL=f"http://127.0.0.1:{srv.server_port}", CRUZAMENTO_API_KEY=CHAVE,
                      CRUZAMENTO_TIMEOUT=5)
    yield estado
    srv.shutdown()
    srv.server_close()


@pytest.fixture()
def empresas_teste(nova_empresa):
    a = nova_empresa("Mercadinho A", responsavel="Natan", cnpj=CNPJ_A)
    b = nova_empresa("Loja B", responsavel="Hellen", tipos_codigos=("NFCE",), cnpj=CNPJ_B)
    return a, b


def lanc(empresa, tipos, codigo):
    return svc_lanc.buscar(empresa.id, COMP, tipos[codigo].id)


# ====================================================================== leitura

def test_buscar_le_o_envelope_trpc_com_a_chave(servidor):
    servidor.dados = resposta(empresa_la(CNPJ_A, "MERCADINHO A", tipo("NFCE_AUTORIZADA", aut=(5, "10.50"))))
    dados = svc.buscar(COMP)
    assert dados["empresas"][0]["cnpj"] == CNPJ_A
    assert servidor.pedidos[-1]["input"] == {"competencia": "2026-08"}
    assert servidor.pedidos[-1]["auth"] == f"Bearer {CHAVE}"
    # Python-urllib é barrado pelo Cloudflare do Manus (403, erro 1010): precisa de User-Agent próprio
    assert "urllib" not in servidor.pedidos[-1]["ua"]
    svc.buscar(COMP, cnpj="12.345.678/0001-90")
    assert servidor.pedidos[-1]["input"] == {"competencia": "2026-08", "cnpj": CNPJ_A}


def test_buscar_explica_os_erros(app, servidor):
    app.config["CRUZAMENTO_API_KEY"] = "outra-chave-qualquer"
    with pytest.raises(svc.ErroCruzamento, match="recusou a chave"):
        svc.buscar(COMP)
    app.config["CRUZAMENTO_API_KEY"] = CHAVE
    servidor.status = 500
    with pytest.raises(svc.ErroCruzamento, match="Banco de dados indisponível"):
        svc.buscar(COMP)
    servidor.status = 200
    servidor.dados = resposta(comp="2026-07")
    with pytest.raises(svc.ErroCruzamento, match="outra competência"):
        svc.buscar(COMP)
    app.config["CRUZAMENTO_URL"] = "http://127.0.0.1:9"  # porta fechada
    with pytest.raises(svc.ErroCruzamento, match="Não foi possível falar"):
        svc.buscar(COMP)
    app.config["CRUZAMENTO_URL"] = ""
    with pytest.raises(svc.ErroCruzamento, match="não configurado"):
        svc.buscar(COMP)


# ====================================================================== prévia

def test_campo_em_branco_aqui_e_igual_a_zero_la(app, db, usuarios, tipos, empresas_teste):
    """Canceladas nunca preenchidas aqui (NULL) e 0 / 0,00 no cruzamento não são diferença."""
    a, _ = empresas_teste
    natan = usuarios["Natan"]
    svc_lanc.salvar_mes(a, COMP, [{"tipo_id": tipos["NFE_ENT"].id, "qtde_autor": "110", "valor_autor": "85587,39",
                                   "qtde_canc": "", "valor_canc": ""}], natan)
    db.session.commit()
    dados = resposta(empresa_la(CNPJ_A, "MERCADINHO A",
                                tipo("NF_ENTRADA_TODAS", aut=(110, "85587.39"), dominio=False)))
    p = svc.montar_previa(dados, COMP, None, natan)
    linha = next(l for l in p.linhas if l.chave == f"{a.id}:NFE_ENT")
    assert linha.situacao == svc.SIT_IGUAL and not linha.marcada


def test_previa_situacoes_por_linha(app, db, usuarios, tipos, empresas_teste):
    a, b = empresas_teste
    natan = usuarios["Natan"]
    # NF-e Saídas já lançada igual; NF-e Entradas lançada diferente e batida
    svc_lanc.salvar_mes(a, COMP, [{"tipo_id": tipos["NFE_SAI"].id, "qtde_autor": "3", "valor_autor": "30,00",
                                   "qtde_canc": "0", "valor_canc": "0"},
                                  {"tipo_id": tipos["NFE_ENT"].id, "qtde_autor": "1", "valor_autor": "1,00",
                                   "qtde_canc": "", "valor_canc": ""}], natan)
    svc_lanc.marcar_bateu(lanc(a, tipos, "NFE_ENT"), True, natan)
    db.session.commit()
    dados = resposta(
        empresa_la(CNPJ_A, "MERCADINHO A",
                   tipo("NF_ENTRADA_TODAS", aut=(2, "2.00"), dominio=False),
                   tipo("NF_SAIDA_TODAS", aut=(3, "30.00"), falta=(0, "0.00")),
                   tipo("NFCE_AUTORIZADA", aut=(100, "1500.25"), canc=(2, "10.00"), falta=(3, "45.90"),
                        notas=[{"numero": "77", "serie": "1", "data": "03/08/2026", "valor": "15.30", "chave": ""}])),
        empresa_la(CNPJ_B, "LOJA B", tipo("NF_ENTRADA_TODAS"), tipo("NF_SAIDA_TODAS", sefaz=False),
                   tipo("NFCE_AUTORIZADA", sefaz=False)),
        empresa_la("11111111000111", "SO NO CRUZAMENTO", tipo("NFCE_AUTORIZADA", aut=(1, "1.00"))),
    )
    p = svc.montar_previa(dados, COMP, None, natan)
    linhas = {l.chave: l for l in p.linhas}
    assert linhas[f"{a.id}:NFE_SAI"].situacao == svc.SIT_IGUAL
    assert linhas[f"{a.id}:NFE_ENT"].situacao == svc.SIT_BATEU
    assert not linhas[f"{a.id}:NFE_ENT"].selecionavel
    nfce = linhas[f"{a.id}:NFCE"]
    assert nfce.situacao == svc.SIT_NOVO and nfce.marcada
    assert nfce.nova.qtde_autor == 100 and nfce.nova.valor_autor == Decimal("1500.25")
    assert (nfce.nova.aj_qtde, nfce.nova.aj_valor) == (3, Decimal("45.90"))
    assert nfce.notas[0]["numero"] == "77"
    # Loja B só usa NFC-e: NF-e Entradas zerada lá (tipo que ela não usa) não aparece; NFC-e sem relatório lá
    loja = next(e for e in p.empresas if e.empresa.id == b.id)
    assert [l.chave for l in loja.linhas] == [f"{b.id}:NFCE"]
    assert linhas[f"{b.id}:NFCE"].situacao == svc.SIT_SEM_DADOS
    assert p.so_la == [{"razao_social": "SO NO CRUZAMENTO", "nome_fantasia": None, "cnpj": "11111111000111"}]
    # filtro de carteira: só as da Hellen
    p_hellen = svc.montar_previa(dados, COMP, usuarios["Hellen"].id, natan)
    assert [e.empresa.nome for e in p_hellen.empresas] == ["Loja B"]
    assert p_hellen.empresas[0].pode_editar is False


def test_previa_lista_empresas_sem_cnpj_e_fora_do_cruzamento(app, usuarios, nova_empresa):
    nova_empresa("Sem CNPJ")
    nova_empresa("Fora", cnpj="22222222000122")
    p = svc.montar_previa(resposta(), COMP, None, usuarios["Natan"])
    assert [e.nome for e in p.sem_cnpj_aqui] == ["Sem CNPJ"]
    assert [e.nome for e in p.fora_do_cruzamento] == ["Fora"]


# ====================================================================== aplicação e versões

def _dados_a(aut=(100, "1500.25"), falta=(3, "45.90")):
    return resposta(empresa_la(CNPJ_A, "MERCADINHO A", tipo("NFCE_AUTORIZADA", aut=aut, canc=(2, "10.00"), falta=falta,
                                                          notas=[{"numero": "77", "serie": "1", "data": "03/08/2026",
                                                                  "valor": "15.30", "chave": ""}])))


def test_aplicar_grava_lancamento_ajuste_e_versao(app, db, usuarios, tipos, empresas_teste):
    a, _ = empresas_teste
    natan = usuarios["Natan"]
    imp = svc.aplicar(_dados_a(), {f"{a.id}:NFCE"}, natan)
    db.session.commit()
    l = lanc(a, tipos, "NFCE")
    assert (l.qtde_autor, l.valor_autor, l.qtde_canc, l.valor_canc) == (100, Decimal("1500.25"), 2, Decimal("10.00"))
    assert l.importacao_id == imp.id
    aj = [x for x in l.ajustes if x.motivo == MOTIVO_CRUZAMENTO]
    assert len(aj) == 1 and (aj[0].qtde, aj[0].valor) == (3, Decimal("45.90"))
    assert "77/1" in aj[0].observacao
    assert l.total_qtde_autor == 103
    versoes = db.session.scalars(select(FonteVersao)).all()
    assert len(versoes) == 1 and versoes[0].importacao_id == imp.id and versoes[0].fonte == "cruzamento"
    assert imp.arquivo.startswith("Cruzamento Domínio × SEFAZ")
    r = svc_imp.resumo(imp)
    assert r["lancamentos_criados"] == 1 and r["ajustes_criados"] == 1

    # mesma leitura de novo: tudo igual, nada a importar
    p = svc.montar_previa(_dados_a(), COMP, None, natan)
    assert p.linhas[0].situacao == svc.SIT_IGUAL and not p.linhas[0].mudou_la


def test_reimportar_mostra_mudou_la_e_troca_so_o_ajuste_do_cruzamento(app, db, usuarios, tipos, empresas_teste):
    a, _ = empresas_teste
    natan = usuarios["Natan"]
    svc.aplicar(_dados_a(), {f"{a.id}:NFCE"}, natan)
    l = lanc(a, tipos, "NFCE")
    svc_lanc.adicionar_ajuste(l, GRUPO_AUTOR, 1, "5,00", natan, motivo=MOTIVO_PADRAO_AJUSTE)
    db.session.commit()

    novos = _dados_a(aut=(101, "1510.25"), falta=(2, "30.60"))
    p = svc.montar_previa(novos, COMP, None, natan)
    linha = p.linhas[0]
    assert linha.situacao == svc.SIT_MUDOU_LA and linha.mudou_la
    assert linha.anterior.qtde_autor == 100 and linha.nova.qtde_autor == 101 and linha.atual.qtde_autor == 100
    assert p.mudaram_la == 1

    imp2 = svc.aplicar(novos, {linha.chave}, natan)
    db.session.commit()
    l = lanc(a, tipos, "NFCE")
    assert l.qtde_autor == 101
    motivos = sorted((x.motivo, x.qtde) for x in l.ajustes)
    assert motivos == [(MOTIVO_PADRAO_AJUSTE, 1), (MOTIVO_CRUZAMENTO, 2)]  # o manual ficou
    assert svc.ultima_versao(a.id, COMP).importacao_id == imp2.id

    # desfazer a 2ª importação volta os números e o ajuste anterior, e a versão anterior volta a valer
    svc_imp.desfazer(imp2, natan)
    db.session.commit()
    l = lanc(a, tipos, "NFCE")
    assert l.qtde_autor == 100
    assert sorted((x.motivo, x.qtde) for x in l.ajustes) == [(MOTIVO_PADRAO_AJUSTE, 1), (MOTIVO_CRUZAMENTO, 3)]
    assert svc.ultima_versao(a.id, COMP).importacao_id != imp2.id


def test_bateu_nunca_e_alterado_e_avisa_que_mudou_la(app, db, usuarios, tipos, empresas_teste):
    a, _ = empresas_teste
    natan = usuarios["Natan"]
    svc.aplicar(_dados_a(), {f"{a.id}:NFCE"}, natan)
    svc_lanc.marcar_bateu(lanc(a, tipos, "NFCE"), True, natan)
    db.session.commit()
    novos = _dados_a(aut=(99, "1400.00"))
    p = svc.montar_previa(novos, COMP, None, natan)
    assert p.linhas[0].situacao == svc.SIT_BATEU and p.mudaram_la_batidas == 1
    assert "Mudou lá" in p.linhas[0].texto
    imp = svc.aplicar(novos, {p.linhas[0].chave}, natan)
    db.session.commit()
    assert lanc(a, tipos, "NFCE").qtde_autor == 100
    assert svc_imp.resumo(imp)["ignorados_bateu"] == 1


def test_carteira_de_outra_pessoa_so_como_substituto(app, db, usuarios, tipos, empresas_teste):
    _, b = empresas_teste
    natan = usuarios["Natan"]
    dados = resposta(empresa_la(CNPJ_B, "LOJA B", tipo("NFCE_AUTORIZADA", aut=(4, "40.00"))))
    imp = svc.aplicar(dados, {f"{b.id}:NFCE"}, natan)
    db.session.commit()
    assert lanc(b, tipos, "NFCE") is None
    assert svc_imp.resumo(imp)["ignorados_outra_carteira"] == 1
    svc.aplicar(dados, {f"{b.id}:NFCE"}, natan, substituto=True)
    db.session.commit()
    assert lanc(b, tipos, "NFCE").qtde_autor == 4


def test_tipo_que_a_empresa_nao_usava_e_adicionado(app, db, usuarios, tipos, empresas_teste):
    _, b = empresas_teste  # Loja B só tem NFC-e
    hellen = usuarios["Hellen"]
    dados = resposta(empresa_la(CNPJ_B, "LOJA B", tipo("NF_ENTRADA_TODAS", aut=(2, "300.00"), dominio=False)))
    p = svc.montar_previa(dados, COMP, None, hellen)
    assert p.linhas[0].situacao == svc.SIT_NOVO
    svc.aplicar(dados, {p.linhas[0].chave}, hellen)
    db.session.commit()
    assert "NF-e Entradas" in [t.nome for t in b.tipos]
    l = lanc(b, tipos, "NFE_ENT")
    assert l.qtde_autor == 2 and not l.ajustes  # Domínio não importado lá: sem ajuste


def test_aplicar_sem_linhas_ou_competencia_futura(app, usuarios):
    with pytest.raises(svc.RegraViolada, match="Marque ao menos"):
        svc.aplicar(_dados_a(), set(), usuarios["Natan"])
    with pytest.raises(svc.RegraViolada, match="futura"):
        svc.aplicar(resposta(comp="2999-01"), {"1:NFCE"}, usuarios["Natan"])


# ====================================================================== telas


