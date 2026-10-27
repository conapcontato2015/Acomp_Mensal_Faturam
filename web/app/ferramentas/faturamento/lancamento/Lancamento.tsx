"use client";
/* Lançamento do mês por empresa: grade como no Excel (Enter avança, colar bloco), ajustes com motivo,
   "bateu" por linha (com confetes quando a empresa fecha), "sem movimento" e gráfico dos últimos meses. */
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useAviso } from "@/components/Avisos";
import { Icone } from "@/components/Icone";
import { Janela } from "@/components/Janela";
import { useSessao } from "@/components/Sessao";
import { AvisoLeitura, Cabecalho, CaixaErro, Carregando, Grupo, Metrica, PilulaStatus, SeletorCompetencia } from "@/components/ui";
import { api, ErroApi, qs } from "@/lib/api";
import { confete } from "@/lib/confete";
import { dataHora, inteiro, lerInteiro, lerNumero, moeda, normalizar, paraCampoInteiro, paraCampoMoeda } from "@/lib/formato";
import type { Ajuste, Competencia, EmpresaResumo, Linha, Referencias, Sentido, Status, Usuario } from "@/lib/tipos";
import { rota, useDados, useFiltros } from "@/lib/usar";

interface PontoEvolucao { competencia: Competencia; rotulo: string; entradas: string; entradasAjuste: string; saidas: string; saidasAjuste: string }
interface Barras { eBase: number; eAj: number; sBase: number; sAj: number }
interface RespLancamento {
  competencia: Competencia; empresa: EmpresaResumo; responsavel: Usuario | null; status: Status; podeEditar: boolean; futura: boolean;
  linhas: Linha[]; proxima: EmpresaResumo | null; minhas: EmpresaResumo[]; outras: EmpresaResumo[];
  evolucao: PontoEvolucao[]; grafico: Barras[]; alturaGrafico: number;
}
interface RespInicio { competencia: Competencia; minhas: (EmpresaResumo & { status: Status })[]; outras: EmpresaResumo[] }

export function Lancamento() {
  const f = useFiltros();
  const empresa = f.get("empresa");
  return empresa ? <TelaEmpresa empresa={empresa} competencia={f.get("competencia")} /> : <EscolherEmpresa competencia={f.get("competencia")} />;
}

/* ------------------------------------------------------------------ escolher a empresa */

function EscolherEmpresa({ competencia }: { competencia: string }) {
  const f = useFiltros();
  const { usuario } = useSessao();
  const nome = usuario?.nome ?? "";
  const ref = useDados<Referencias>(`/referencias${qs({ competencia })}`);
  const ini = useDados<RespInicio>(`/lancamento/inicio${qs({ competencia })}`);
  const [busca, setBusca] = useState("");
  const d = ini.dados;
  const termo = normalizar(busca);
  const casa = (e: EmpresaResumo) => !termo || normalizar(e.nome).includes(termo) || (e.cnpj ?? "").includes(busca.replace(/\D/g, "") || "§");
  const minhas = d ? d.minhas.filter(casa) : [];
  const outras = d ? d.outras.filter(casa) : [];
  const unica = minhas.length + outras.length === 1 ? (minhas[0] ?? outras[0]) : null;

  return (
    <>
      <Cabecalho titulo="Lançamento" descricao="Escolha a empresa para carregar os números do mês."
                 acoes={ref.dados && d ? <SeletorCompetencia valor={d.competencia.valor} opcoes={ref.dados.competencias} onChange={(v) => f.set({ competencia: v })} /> : null} />
      {ini.erro ? <CaixaErro mensagens={ini.erro.mensagens} onTentar={() => void ini.recarregar()} /> : null}
      {!d && ini.carregando ? <Carregando /> : null}
      {d ? (
        !d.minhas.length && !d.outras.length ? (
          <div className="card vazio">Nenhuma empresa cadastrada. <Link className="underline" href={rota("empresas")}>Cadastre empresas</Link>.</div>
        ) : (
          <>
            <div className="card flex flex-wrap items-end gap-3 p-4">
              <label className="campo flex-1 basis-[320px]">
                <span>Pesquisar empresa</span>
                <input className="entrada" value={busca} autoFocus placeholder="Nome ou CNPJ…" onChange={(e) => setBusca(e.target.value)}
                       onKeyDown={(e) => { if (e.key === "Enter" && unica) f.set({ empresa: unica.id }); }} />
              </label>
              <span className="pb-2 text-[13px] text-[var(--ink-3)]">{unica ? "Enter abre a empresa encontrada." : `${minhas.length + outras.length} empresa(s)`}</span>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Grupo titulo={`Carteira de ${nome} em ${d.competencia.curta}`}>
                {minhas.length ? (
                  <ul className="divide-y divide-[var(--line)]">
                    {minhas.map((e) => (
                      <li key={e.id}>
                        <Link href={rota("lancamento", { empresa: e.id, competencia: d.competencia.valor })}
                              className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-[var(--surface-2)]">
                          <span className="min-w-0 truncate font-medium">{e.nome}</span>
                          <PilulaStatus status={e.status} />
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : <div className="vazio">{termo ? `Nenhuma empresa da carteira de ${nome} com esse nome.` : `Carteira de ${nome} vazia neste mês.`}</div>}
              </Grupo>
              <Grupo titulo="Outras carteiras" acoes={<span className="badge">somente leitura</span>}>
                {outras.length ? (
                  <ul className="max-h-[480px] divide-y divide-[var(--line)] overflow-y-auto">
                    {outras.map((e) => (
                      <li key={e.id}>
                        <Link href={rota("lancamento", { empresa: e.id, competencia: d.competencia.valor })}
                              className="flex items-center justify-between gap-3 px-4 py-3 text-[var(--ink-2)] hover:bg-[var(--surface-2)]">
                          <span className="min-w-0 truncate">{e.nome}</span>
                          <Icone nome="seta" className="shrink-0 text-[var(--ink-3)]" />
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : <div className="vazio">Nenhuma.</div>}
              </Grupo>
            </div>
          </>
        )
      ) : null}
    </>
  );
}

/* ------------------------------------------------------------------ tela da empresa */

function TelaEmpresa({ empresa, competencia }: { empresa: string; competencia: string }) {
  const ref = useDados<Referencias>(`/referencias${qs({ competencia })}`);
  const lanc = useDados<RespLancamento>(`/lancamento${qs({ empresa, competencia })}`);
  if (lanc.erro) {
    return (
      <>
        <Cabecalho titulo="Lançamento" />
        <CaixaErro mensagens={lanc.erro.mensagens} onTentar={lanc.erro.status === 404 ? undefined : () => void lanc.recarregar()} />
        <Link className="btn self-start" href={rota("lancamento", { competencia })}>Escolher outra empresa</Link>
      </>
    );
  }
  if (!lanc.dados || !ref.dados) return <Carregando />;
  const d = lanc.dados;
  return <Editor key={`${d.empresa.id}-${d.competencia.valor}`} inicial={d} refs={ref.dados} />;
}

type Campo = "qtdeAutor" | "valorAutor" | "qtdeCanc" | "valorCanc";
const CAMPOS: Campo[] = ["qtdeAutor", "valorAutor", "qtdeCanc", "valorCanc"];
const ROTULO_CAMPO: Record<Campo, string> = { qtdeAutor: "Quantidade autorizada", valorAutor: "Valor autorizado", qtdeCanc: "Quantidade cancelada", valorCanc: "Valor cancelado" };
type Textos = Record<Campo, string>;
const SENTIDOS: { valor: Sentido; titulo: string }[] = [
  { valor: "E", titulo: "Entradas" }, { valor: "S", titulo: "Saídas" }, { valor: "O", titulo: "Outros (fora dos totais de entradas e saídas)" },
];

const textosDe = (l: Linha): Textos => ({
  qtdeAutor: paraCampoInteiro(l.qtdeAutor), valorAutor: paraCampoMoeda(l.valorAutor),
  qtdeCanc: paraCampoInteiro(l.qtdeCanc), valorCanc: paraCampoMoeda(l.valorCanc),
});
const mapaTextos = (ls: Linha[]) => Object.fromEntries(ls.map((l) => [l.tipo.id, textosDe(l)])) as Record<number, Textos>;
const mesmo = (a: string, b: string) => {
  const x = lerNumero(a), y = lerNumero(b);
  return x === y || (x !== null && y !== null && !Number.isNaN(x) && x === y);
};

interface Validacao { erro: string; aviso: string; qa: number | null; va: number | null; qc: number | null; vc: number | null; invalidos: Campo[] }

function validar(nome: string, t: Textos): Validacao {
  const iqa = lerInteiro(t.qtdeAutor), iqc = lerInteiro(t.qtdeCanc);
  const qa = iqa === "fracao" ? NaN : iqa, qc = iqc === "fracao" ? NaN : iqc;
  const va = lerNumero(t.valorAutor), vc = lerNumero(t.valorCanc);
  const nums: Record<Campo, number | null> = { qtdeAutor: qa, valorAutor: va, qtdeCanc: qc, valorCanc: vc };
  const invalidos = CAMPOS.filter((c) => Number.isNaN(nums[c]) || (nums[c] ?? 0) < 0);
  let erro = "";
  if (iqa === "fracao" || iqc === "fracao") erro = "Quantidade deve ser número inteiro.";
  else if (CAMPOS.some((c) => Number.isNaN(nums[c]))) erro = "Só números são aceitos. Para uma diferença, use o botão de ajuste.";
  else if (CAMPOS.some((c) => (nums[c] ?? 0) < 0)) erro = "Números do relatório não podem ser negativos (use um ajuste negativo).";
  else if ((qa === null) !== (va === null)) erro = `${nome} autorizadas: informe quantidade e valor juntos (valor sem quantidade some do resumo).`;
  else if ((qc === null) !== (vc === null)) erro = `${nome} canceladas: informe quantidade e valor juntos.`;
  if (!erro && (qa === null) !== (va === null)) invalidos.push(qa === null ? "qtdeAutor" : "valorAutor");
  const aviso = !erro && qa !== null && qc !== null && qc > qa ? "Mais canceladas que autorizadas (pode ser nota do mês anterior)." : "";
  return { erro, aviso, qa, va, qc, vc, invalidos };
}

const somaAj = (aj: Ajuste[], grupo: "AUTOR" | "CANC", campo: "qtde" | "valor") =>
  aj.filter((a) => a.grupo === grupo).reduce((s, a) => s + Number(a[campo] || 0), 0);

function Editor({ inicial, refs }: { inicial: RespLancamento; refs: Referencias }) {
  const f = useFiltros();
  const { usuario } = useSessao();
  const avisar = useAviso();
  const d = inicial;
  const comp = d.competencia.valor;
  const [linhas, setLinhas] = useState<Linha[]>(d.linhas);
  const [textos, setTextos] = useState<Record<number, Textos>>(() => mapaTextos(d.linhas));
  const [iniciais, setIniciais] = useState<Record<number, Textos>>(() => mapaTextos(d.linhas));
  const [status, setStatus] = useState<Status>(d.status);
  const [substituto, setSubstituto] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [ajusteAberto, setAjusteAberto] = useState<{ tipoId: number; grupo: "AUTOR" | "CANC" } | null>(null);
  const tabela = useRef<HTMLTableElement>(null);
  const btnSalvar = useRef<HTMLButtonElement>(null);

  const editavel = !d.futura && (d.podeEditar || substituto);
  const ordem = useMemo(() => SENTIDOS.flatMap((s) => linhas.filter((l) => l.tipo.sentido === s.valor)), [linhas]);
  const validacoes = useMemo(() => Object.fromEntries(linhas.map((l) => [l.tipo.id, validar(l.tipo.nome, textos[l.tipo.id])])) as Record<number, Validacao>, [linhas, textos]);
  const suja = (tid: number) => CAMPOS.some((c) => !mesmo(textos[tid][c], iniciais[tid][c]));
  const algumaSuja = linhas.some((l) => suja(l.tipo.id));

  // Aviso do navegador ao sair com digitação não salva.
  useEffect(() => {
    if (!algumaSuja) return;
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [algumaSuja]);

  const totais = useMemo(() => {
    let ent = 0, sai = 0, canc = 0, ok = 0, comMov = 0;
    const porLinha: Record<number, { temA: boolean; temC: boolean; tqa: number; tva: number; tqc: number; tvc: number }> = {};
    for (const l of linhas) {
      const v = validacoes[l.tipo.id];
      const n = (x: number | null) => (x === null || Number.isNaN(x) ? 0 : x);
      const tqa = n(v.qa) + somaAj(l.ajustes, "AUTOR", "qtde"), tva = n(v.va) + somaAj(l.ajustes, "AUTOR", "valor");
      const tqc = n(v.qc) + somaAj(l.ajustes, "CANC", "qtde"), tvc = n(v.vc) + somaAj(l.ajustes, "CANC", "valor");
      const temA = v.qa !== null || l.ajustes.some((a) => a.grupo === "AUTOR");
      const temC = v.qc !== null || l.ajustes.some((a) => a.grupo === "CANC");
      porLinha[l.tipo.id] = { temA, temC, tqa, tva, tqc, tvc };
      // "Outros" (ex.: recebimento de caixa) não entra nos totais de entradas, saídas e canceladas.
      if (l.tipo.sentido === "E") ent += tva; else if (l.tipo.sentido === "S") sai += tva;
      if (l.tipo.sentido !== "O") canc += tvc;
      if (temA || temC) { comMov++; if (l.bateu) ok++; }
    }
    return { ent, sai, canc, ok, comMov, porLinha };
  }, [linhas, validacoes]);

  const aplicarResposta = (novas: Linha[]) => {
    setLinhas(novas);
    setTextos(mapaTextos(novas));
    setIniciais(mapaTextos(novas));
  };
  const trocarLinha = (nova: Linha) => setLinhas((ls) => ls.map((l) => (l.tipo.id === nova.tipo.id ? nova : l)));
  const falha = (e: unknown) => avisar(e instanceof ErroApi ? e.mensagens.join(" ") : String(e), "erro");

  const mudar = (tid: number, campo: Campo, valor: string) => setTextos((t) => ({ ...t, [tid]: { ...t[tid], [campo]: valor } }));

  const salvar = async () => {
    if (linhas.some((l) => validacoes[l.tipo.id].erro)) { avisar("Corrija as linhas destacadas antes de salvar.", "erro"); return; }
    setSalvando(true);
    try {
      const r = await api<{ alterados: number; avisos: string[]; status: Status; linhas: Linha[] }>(`/lancamento/${d.empresa.id}/${comp}`, "PUT", {
        substituto, linhas: linhas.map((l) => ({ tipoId: l.tipo.id, ...textos[l.tipo.id] })),
      });
      aplicarResposta(r.linhas);
      setStatus(r.status);
      avisar(r.alterados ? `Salvo: ${r.alterados} linha(s) alterada(s).${r.avisos.length ? " " + r.avisos.join(" ") : ""}` : "Nada mudou.");
    } catch (e) { falha(e); } finally { setSalvando(false); }
  };

  const semMovimento = async (valor: "sem_movimento" | "pendente") => {
    try {
      const r = await api<{ status: Status }>(`/fechamento/${d.empresa.id}/${comp}`, "PUT", { status: valor, substituto });
      setStatus(r.status);
      avisar(valor === "sem_movimento" ? "Marcada como sem movimento no mês." : "\"Sem movimento\" desfeito.");
    } catch (e) { falha(e); }
  };

  const marcarBateu = async (l: Linha, bateu: boolean, alvo: HTMLElement) => {
    if (!l.id) return;
    trocarLinha({ ...l, bateu }); // marca na hora; volta atrás se o servidor recusar
    try {
      const r = await api<{ bateu: boolean; empresa: { linhas: number; bateram: number } }>(`/lancamentos/${l.id}/bateu`, "PUT", { bateu, substituto });
      trocarLinha({ ...l, bateu: r.bateu });
      avisar(bateu ? `${l.tipo.nome}: bateu.` : `${l.tipo.nome}: voltou para "a conferir".`);
      if (bateu && r.empresa.linhas > 0 && r.empresa.bateram === r.empresa.linhas) confete(alvo); // parabéns: a empresa fechou
    } catch (e) { trocarLinha(l); falha(e); }
  };

  // Enter avança para a próxima célula editável, como no Excel.
  const teclar = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const todas = Array.from(tabela.current?.querySelectorAll<HTMLInputElement>("input.celula:not([readonly])") ?? []);
    const i = todas.indexOf(e.currentTarget);
    if (todas[i + 1]) todas[i + 1].focus(); else btnSalvar.current?.focus();
  };

  // Colar um bloco copiado do Excel (linhas × colunas) a partir da célula atual.
  const colar = (e: React.ClipboardEvent<HTMLInputElement>, tid: number, campo: Campo) => {
    const texto = e.clipboardData.getData("text");
    if (!texto || (!texto.includes("\t") && !texto.includes("\n"))) return;
    e.preventDefault();
    const grade = texto.replace(/\r/g, "").split("\n").filter((x) => x.length).map((x) => x.split("\t"));
    const i0 = ordem.findIndex((l) => l.tipo.id === tid), c0 = CAMPOS.indexOf(campo);
    setTextos((t) => {
      const novo = { ...t };
      grade.forEach((lin, di) => {
        const l = ordem[i0 + di];
        if (!l || l.bateu) return;
        const cel = { ...novo[l.tipo.id] };
        lin.forEach((v, dj) => { const c = CAMPOS[c0 + dj]; if (c) cel[c] = v.trim(); });
        novo[l.tipo.id] = cel;
      });
      return novo;
    });
  };

  const trocarEmpresa = (params: Record<string, string | number>) => {
    if (algumaSuja && !window.confirm("Há números digitados e não salvos. Sair mesmo assim?")) return;
    f.set(params);
  };

  const dono = d.responsavel?.nome ?? "outra pessoa";
  const linhaAjuste = ajusteAberto ? linhas.find((l) => l.tipo.id === ajusteAberto.tipoId) ?? null : null;

  return (
    <>
      <Cabecalho
        sobre={<Link href={rota("lancamento", { competencia: comp })} className="hover:underline">Lançamento</Link>}
        titulo={<span className="flex flex-wrap items-center gap-3">{d.empresa.nome} <PilulaStatus status={status} /></span>}
        descricao={<>CNPJ {d.empresa.cnpjFormatado || "não informado"} · Responsável em {d.competencia.curta}: <strong>{d.responsavel?.nome ?? "—"}</strong></>}
        acoes={
          <div className="flex flex-wrap items-end gap-3">
            <SeletorCompetencia valor={comp} opcoes={refs.competencias} onChange={(v) => trocarEmpresa({ competencia: v })} />
            <label className="campo min-w-[260px]">
              <span>Empresa</span>
              <select className="entrada" value={d.empresa.id} onChange={(e) => trocarEmpresa({ empresa: e.target.value })}>
                {d.minhas.length ? <optgroup label={`Carteira de ${usuario?.nome ?? ""}`}>{d.minhas.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}</optgroup> : null}
                <optgroup label="Outras carteiras (somente leitura)">{d.outras.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}</optgroup>
              </select>
            </label>
          </div>
        } />

      {d.futura ? <div className="aviso aviso-danger" role="alert"><Icone nome="alerta" className="mt-0.5 shrink-0 text-[var(--danger)]" />Competência futura: não é possível lançar.</div> : null}
      {!d.podeEditar && !d.futura ? (
        <AvisoLeitura dono={dono} substituto={
          <label className="flex cursor-pointer items-center gap-2 text-[14px] font-medium">
            <input type="checkbox" className="check" checked={substituto} onChange={(e) => setSubstituto(e.target.checked)} />
            Lançar como substituto (estou cobrindo esta carteira)
          </label>} />
      ) : null}

      <div className="card flex flex-wrap items-center justify-between gap-3 p-4">
        <span className="text-[14px] text-[var(--ink-2)]">
          Origem dos números: <strong className="text-[var(--ink)]">relatório da SEFAZ</strong>, digitação manual ou cruzamento Domínio × SEFAZ.
          Ajustes = arquivos da empresa que não constam no relatório.
        </span>
        <Link className="btn" href={rota("importacao/cruzamento", { competencia: comp, empresa: d.empresa.id, ver: 1 })}
              title="NF-e Entradas, NF-e Saídas, NFC-e e o ajuste sugerido, com prévia antes de gravar">
          <Icone nome="nuvem" /> Buscar no cruzamento
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Metrica icone="importar" rotulo="Entradas autorizadas (R$)" valor={moeda(totais.ent)} />
        <Metrica icone="seta" rotulo="Saídas autorizadas (R$)" valor={moeda(totais.sai)} tom="brand" />
        <Metrica icone="fechar" rotulo="Canceladas (R$)" valor={moeda(totais.canc)} />
        <Metrica icone="ok" rotulo="Linhas que bateram" valor={`${totais.ok} de ${totais.comMov}`}
                 tom={totais.comMov && totais.ok === totais.comMov ? "ok" : totais.comMov ? "warn" : undefined} />
      </div>

      <Grupo>
        {linhas.length ? (
          <div className="rolagem">
            <table ref={tabela} className="tabela min-w-[1100px]">
              <thead>
                <tr>
                  <th />
                  <th colSpan={4} className="text-center !text-[var(--ink-2)]">Autorizadas</th>
                  <th colSpan={4} className="border-l border-[var(--line)] text-center !text-[var(--ink-2)]">Canceladas</th>
                  <th />
                </tr>
                <tr>
                  <th>Tipo</th><th className="num">Qtde</th><th className="num">Valor (R$)</th><th className="text-center">Ajuste</th><th className="num">Total</th>
                  <th className="num border-l border-[var(--line)]">Qtde</th><th className="num">Valor (R$)</th><th className="text-center">Ajuste</th><th className="num">Total</th>
                  <th className="text-center">Bateu</th>
                </tr>
              </thead>
              <tbody>
                {SENTIDOS.map((s) => {
                  const grupo = linhas.filter((l) => l.tipo.sentido === s.valor);
                  if (!grupo.length) return null;
                  return [
                    <tr key={`s-${s.valor}`} className="sentido"><td colSpan={10}>{s.titulo}</td></tr>,
                    ...grupo.flatMap((l) => {
                      const tid = l.tipo.id, v = validacoes[tid], t = totais.porLinha[tid];
                      const travada = l.bateu, somenteLer = !editavel || travada, sujaL = suja(tid);
                      const celula = (c: Campo) => (
                        <td className="!px-1.5">
                          <input className={`celula ${c.startsWith("valor") ? "min-w-[124px]" : ""}`} value={textos[tid][c]} readOnly={somenteLer} inputMode={c.startsWith("qtde") ? "numeric" : "decimal"}
                                 aria-label={`${ROTULO_CAMPO[c]} · ${l.tipo.nome}`} aria-invalid={v.invalidos.includes(c) || undefined}
                                 onChange={(e) => mudar(tid, c, e.target.value)} onKeyDown={teclar} onPaste={(e) => colar(e, tid, c)} />
                        </td>
                      );
                      const ajuste = (g: "AUTOR" | "CANC") => {
                        const lista = l.ajustes.filter((a) => a.grupo === g);
                        const q = somaAj(lista, g, "qtde");
                        return (
                          <td className="text-center">
                            <button type="button" className="btn-ajuste" data-tem={lista.length > 0} onClick={() => setAjusteAberto({ tipoId: tid, grupo: g })}
                                    aria-label={`Ajustes de ${g === "AUTOR" ? "autorizadas" : "canceladas"} · ${l.tipo.nome}`}>
                              {lista.length ? `${q >= 0 ? "+" : ""}${inteiro(q)} · ${moeda(somaAj(lista, g, "valor"))}` : "Ajustar"}
                            </button>
                          </td>
                        );
                      };
                      const bateuBloq = !editavel || !l.id || sujaL;
                      const out = [
                        <tr key={tid} className={travada ? "travada" : undefined}>
                          <td className="whitespace-nowrap font-medium">{l.tipo.nome}</td>
                          {celula("qtdeAutor")}{celula("valorAutor")}{ajuste("AUTOR")}
                          <td className="num whitespace-nowrap font-semibold">{t.temA ? <>{inteiro(t.tqa)} · {moeda(t.tva)}</> : "—"}</td>
                          {celula("qtdeCanc")}{celula("valorCanc")}{ajuste("CANC")}
                          <td className="num whitespace-nowrap font-semibold">{t.temC ? <>{inteiro(t.tqc)} · {moeda(t.tvc)}</> : "—"}</td>
                          <td className="text-center">
                            <input type="checkbox" className="check !h-5 !w-5" checked={l.bateu} disabled={bateuBloq}
                                   title={sujaL ? "Salve as alterações antes de marcar" : l.bateu && l.bateuPor ? `Marcado por ${l.bateuPor.nome}` : undefined}
                                   aria-label={`${l.tipo.nome} bateu com o sistema contábil`}
                                   onChange={(e) => void marcarBateu(l, e.target.checked, e.currentTarget)} />
                          </td>
                        </tr>,
                      ];
                      if (v.erro || v.aviso) {
                        out.push(
                          <tr key={`${tid}-msg`}>
                            <td colSpan={10} className={`!pt-0 text-[13px] ${v.erro ? "font-medium text-[var(--danger)]" : "text-[var(--info)]"}`}>
                              {v.erro ? `⚠ ${v.erro}` : `ℹ ${v.aviso}`}
                            </td>
                          </tr>,
                        );
                      }
                      return out;
                    }),
                  ];
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="vazio">Esta empresa não tem tipos de documento definidos. <Link className="underline" href={rota("empresas/editar", { id: d.empresa.id })}>Definir tipos usados</Link>.</div>
        )}
      </Grupo>

      <div className="nao-imprimir flex flex-wrap items-center justify-between gap-3">
        <span className="text-[13px] text-[var(--ink-3)]">
          Enter avança como no Excel; dá para colar um bloco copiado da planilha. Diferenças contra os arquivos da empresa entram como ajuste, com motivo. Linha que bateu fica travada.
        </span>
        <div className="flex flex-wrap gap-2">
          {status === "sem_movimento" ? <button className="btn" type="button" disabled={!editavel} onClick={() => void semMovimento("pendente")}>Desfazer &quot;sem movimento&quot;</button>
            : status === "pendente" ? <button className="btn" type="button" disabled={!editavel} onClick={() => void semMovimento("sem_movimento")}>Marcar sem movimento</button> : null}
          <button ref={btnSalvar} className="btn btn-solid" type="button" disabled={!editavel || salvando || !linhas.length} onClick={() => void salvar()}>
            {salvando ? "Salvando…" : algumaSuja ? "Salvar alterações" : "Salvar"}
          </button>
          {d.proxima ? (
            <button type="button" className="btn" onClick={() => trocarEmpresa({ empresa: d.proxima!.id })}>Próxima empresa <Icone nome="seta" /></button>
          ) : null}
        </div>
      </div>

      <Grafico evolucao={d.evolucao} grafico={d.grafico} altura={d.alturaGrafico} />

      <JanelaAjustes
        aberta={!!ajusteAberto && !!linhaAjuste} linha={linhaAjuste} grupo={ajusteAberto?.grupo ?? "AUTOR"}
        travada={!editavel || !!linhaAjuste?.bateu} motivos={refs.motivosAjuste} empresa={d.empresa} competencia={d.competencia}
        substituto={substituto} aoFechar={() => setAjusteAberto(null)}
        aoMudar={(nova, st) => { trocarLinha(nova); if (st) setStatus(st); }} falha={falha} />
    </>
  );
}

/* ------------------------------------------------------------------ ajustes */

function JanelaAjustes({ aberta, linha, grupo, travada, motivos, empresa, competencia, substituto, aoFechar, aoMudar, falha }: {
  aberta: boolean; linha: Linha | null; grupo: "AUTOR" | "CANC"; travada: boolean; motivos: string[]; empresa: EmpresaResumo;
  competencia: Competencia; substituto: boolean; aoFechar: () => void; aoMudar: (l: Linha, s?: Status) => void; falha: (e: unknown) => void;
}) {
  const avisar = useAviso();
  const vazio = { qtde: "", valor: "", motivo: motivos[0] ?? "", observacao: "" };
  const [form, setForm] = useState(vazio);
  const [removendo, setRemovendo] = useState<number | null>(null);
  const [enviando, setEnviando] = useState(false);
  useEffect(() => { if (aberta) { setForm({ qtde: "", valor: "", motivo: motivos[0] ?? "", observacao: "" }); setRemovendo(null); } }, [aberta, motivos]);
  if (!linha) return <Janela aberta={false} aoFechar={aoFechar} titulo="Ajuste"><span /></Janela>;
  const lista = linha.ajustes.filter((a) => a.grupo === grupo);

  const q = lerInteiro(form.qtde), v = lerNumero(form.valor);
  const erro = form.qtde === "" && form.valor === "" ? "" : q === "fracao" ? "Quantidade deve ser inteira." :
    (q !== null && Number.isNaN(q)) || (v !== null && Number.isNaN(v)) ? "Só números (use - para reduzir)." : "";

  const salvar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (erro || (form.qtde === "" && form.valor === "")) return;
    setEnviando(true);
    try {
      const r = await api<{ ajuste: Ajuste; linha: Linha; status: Status }>(`/lancamento/${empresa.id}/${competencia.valor}/${linha.tipo.id}/ajustes`, "POST", {
        grupo, qtde: form.qtde, valor: form.valor, motivo: form.motivo, observacao: form.observacao, substituto,
      });
      aoMudar(r.linha, r.status);
      setForm({ ...vazio, motivo: form.motivo });
      avisar("Ajuste salvo.");
    } catch (er) { falha(er); } finally { setEnviando(false); }
  };

  const remover = async (a: Ajuste) => {
    try {
      const r = await api<{ linha: Linha }>(`/ajustes/${a.id}${qs({ substituto: substituto ? "true" : "" })}`, "DELETE");
      aoMudar(r.linha);
      setRemovendo(null);
      avisar("Ajuste removido (fica no histórico).");
    } catch (er) { falha(er); }
  };

  return (
    <Janela aberta={aberta} aoFechar={aoFechar}
            titulo={`Ajuste · ${linha.tipo.nome} · ${grupo === "AUTOR" ? "Autorizadas" : "Canceladas"}`}
            subtitulo={`${empresa.nome} · ${competencia.curta}`}>
      <div className="flex flex-col gap-2">
        {lista.length ? lista.map((a) => (
          <div key={a.id} className="flex items-start justify-between gap-3 rounded-xl border border-[var(--line)] p-3">
            <div className="min-w-0">
              <strong className="tabular-nums">{a.qtde >= 0 ? "+" : ""}{inteiro(a.qtde)} docs · R$ {moeda(a.valor)}</strong>
              <div className="text-[13px] text-[var(--ink-3)]">
                {a.motivo}{a.observacao ? ` — ${a.observacao}` : ""} · {a.criadoPor?.nome ?? "—"} em {dataHora(a.criadoEm)}
              </div>
            </div>
            {!travada ? (
              removendo === a.id ? (
                <span className="flex shrink-0 gap-1">
                  <button type="button" className="btn btn-sm" onClick={() => setRemovendo(null)}>Não</button>
                  <button type="button" className="btn btn-sm border-[var(--danger)] text-[var(--danger)]" onClick={() => void remover(a)}>Remover</button>
                </span>
              ) : <button type="button" className="btn btn-quiet btn-sm shrink-0" onClick={() => setRemovendo(a.id)}>Remover</button>
            ) : null}
          </div>
        )) : <span className="text-[13px] text-[var(--ink-3)]">Nenhum ajuste nesta linha.</span>}
      </div>

      {travada ? (
        <p className="text-[13px] text-[var(--ink-3)]">{linha.bateu ? "Linha marcada como \"bateu\": desmarque para ajustar." : "Somente leitura."}</p>
      ) : (
        <form className="flex flex-col gap-3 border-t border-[var(--line)] pt-4" onSubmit={(e) => void salvar(e)}>
          <div className="grid grid-cols-2 gap-3">
            <label className="campo"><span>Quantidade</span>
              <input className="entrada text-right" inputMode="numeric" placeholder="+0" value={form.qtde} autoFocus onChange={(e) => setForm({ ...form, qtde: e.target.value })} /></label>
            <label className="campo"><span>Valor (R$)</span>
              <input className="entrada text-right" inputMode="decimal" placeholder="0,00" value={form.valor} onChange={(e) => setForm({ ...form, valor: e.target.value })} /></label>
          </div>
          <label className="campo"><span>Motivo</span>
            <select className="entrada" value={form.motivo} onChange={(e) => setForm({ ...form, motivo: e.target.value })}>
              {motivos.map((m) => <option key={m}>{m}</option>)}
            </select></label>
          <label className="campo"><span>Observação</span>
            <textarea className="entrada" rows={2} placeholder="Ex.: chaves conferidas no lote de XML" value={form.observacao} onChange={(e) => setForm({ ...form, observacao: e.target.value })} /></label>
          {erro ? <span className="text-[13px] font-medium text-[var(--danger)]">{erro}</span> : null}
          <span className="text-[13px] text-[var(--ink-3)]">Use sinal negativo para reduzir (ex.: -3). O ajuste soma ao número do relatório; o original não muda.</span>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn" onClick={aoFechar}>Fechar</button>
            <button type="submit" className="btn btn-solid" disabled={enviando || !!erro || (form.qtde === "" && form.valor === "")}>{enviando ? "Salvando…" : "Salvar ajuste"}</button>
          </div>
        </form>
      )}
    </Janela>
  );
}

/* ------------------------------------------------------------------ gráfico */

function Grafico({ evolucao, grafico, altura }: { evolucao: PontoEvolucao[]; grafico: Barras[]; altura: number }) {
  const comAjuste = Array.from(new Set(evolucao.filter((p) => Number(p.entradasAjuste) || Number(p.saidasAjuste)).map((p) => p.rotulo)));
  const total = (b: string, a: string) => Number(b) + Number(a);
  return (
    <Grupo titulo="Entradas e saídas autorizadas por mês"
           acoes={<div className="legenda">
             <span><i style={{ background: "var(--ink)" }} />Entradas</span>
             <span><i style={{ background: "var(--brand)" }} />Saídas</span>
             <span><i style={{ background: "repeating-linear-gradient(45deg,#a8a398 0 3px,#ffc799 3px 6px)" }} />Parte de ajuste</span>
           </div>}>
      <div className="flex flex-col gap-3 p-4">
        <span className="text-[13px] text-[var(--ink-3)]">
          Todos os tipos. {comAjuste.length ? `Meses com ajuste: ${comAjuste.join(", ")}. ` : ""}Passe o mouse nas barras para ver os valores.
        </span>
        <div className="grafico" style={{ height: altura }} role="img"
             aria-label={evolucao.map((p) => `${p.rotulo}: entradas R$ ${moeda(total(p.entradas, p.entradasAjuste))}, saídas R$ ${moeda(total(p.saidas, p.saidasAjuste))}`).join("; ")}>
          {evolucao.map((p, i) => {
            const g = grafico[i] ?? { eBase: 0, eAj: 0, sBase: 0, sAj: 0 };
            return (
              <div key={p.competencia.valor} className="mes">
                <div className="coluna" title={`${p.rotulo} · Entradas R$ ${moeda(total(p.entradas, p.entradasAjuste))}${Number(p.entradasAjuste) ? ` (ajuste R$ ${moeda(p.entradasAjuste)})` : ""}`}>
                  <div className="seg" style={{ height: g.eAj, background: "#a8a398" }} />
                  <div className="seg" style={{ height: g.eBase, background: "var(--ink)", borderRadius: g.eAj ? 0 : "5px 5px 0 0" }} />
                </div>
                <div className="coluna" title={`${p.rotulo} · Saídas R$ ${moeda(total(p.saidas, p.saidasAjuste))}${Number(p.saidasAjuste) ? ` (ajuste R$ ${moeda(p.saidasAjuste)})` : ""}`}>
                  <div className="seg" style={{ height: g.sAj, background: "#ffc799" }} />
                  <div className="seg" style={{ height: g.sBase, background: "var(--brand)", borderRadius: g.sAj ? 0 : "5px 5px 0 0" }} />
                </div>
              </div>
            );
          })}
        </div>
        <div className="grafico-rotulos">
          {evolucao.map((p, i) => <span key={p.competencia.valor} className={i === evolucao.length - 1 ? "atual" : undefined}>{p.rotulo}</span>)}
        </div>
      </div>
    </Grupo>
  );
}

