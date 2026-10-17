"use client";
/* Empresas: responsável da carteira (troca direto na tabela, valendo a partir de uma competência) e os tipos
   de documento que cada uma usa. O cadastro pode vir do Conap Ferramentas (EMPRESAS_FONTE=plataforma). */
import Link from "next/link";
import { useEffect, useState } from "react";
import { useAviso } from "@/components/Avisos";
import { Icone } from "@/components/Icone";
import { useSessao } from "@/components/Sessao";
import { BarraFiltros, Cabecalho, CaixaErro, Carregando, Grupo, SeletorCarteira, TagTipo } from "@/components/ui";
import { api, ErroApi, qs } from "@/lib/api";
import type { Competencia, EmpresaResumo, Referencias, TipoDocumento, Usuario } from "@/lib/tipos";
import { ROTULO_ORIGEM } from "@/lib/tipos";
import { rota, useDados, useFiltros } from "@/lib/usar";

interface LinhaEmpresa extends EmpresaResumo { externalId: string | null; responsavel: Usuario | null; origem: string | null; tipos: TipoDocumento[] }
interface RespEmpresas {
  carteira: string; busca: string; inativas: boolean; inicioPadrao: Competencia; competencias: Competencia[];
  fontePlataforma: boolean; empresas: LinhaEmpresa[];
}

export function Empresas() {
  const { usuario, sessao } = useSessao();
  const f = useFiltros();
  const carteira = f.get("carteira") || "todos", busca = f.get("busca"), inativas = f.get("inativas") !== "0";
  const ref = useDados<Referencias>("/referencias");
  const lista = useDados<RespEmpresas>(`/empresas${qs({ carteira, busca, inativas: inativas ? "true" : "false" })}`);
  const [texto, setTexto] = useState(busca);
  const [inicio, setInicio] = useState("");
  const d = lista.dados;

  // Busca enquanto digita (com uma pequena espera).
  useEffect(() => {
    if (texto === busca) return;
    const t = setTimeout(() => f.set({ busca: texto }), 350);
    return () => clearTimeout(t);
  }, [texto]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (d && !inicio) setInicio(d.inicioPadrao.valor); }, [d, inicio]);

  const r = sessao?.recursos;
  const plataforma = d?.fontePlataforma ?? r?.empresasFonte === "plataforma";

  return (
    <>
      <Cabecalho titulo="Empresas" descricao="Responsável da carteira e tipos de documento que cada empresa usa. Só esses tipos aparecem no lançamento."
                 acoes={<>
                   <Link className="btn" href={rota("empresas/responsaveis")}>Importar responsáveis</Link>
                   <Link className="btn" href={rota("importacao")}>Importar planilha antiga</Link>
                   {plataforma ? <Link className="btn btn-solid" href={rota("empresas/plataforma")}><Icone nome="nuvem" /> Cadastro do Conap Ferramentas</Link>
                     : <Link className="btn btn-solid" href={rota("empresas/editar")}><Icone nome="mais" /> Nova empresa</Link>}
                 </>} />

      {r ? (
        <div className="aviso aviso-info" role="status">
          <Icone nome="info" className="mt-0.5 shrink-0 text-[var(--info)]" />
          <div className="flex flex-1 flex-col gap-1.5">
            {plataforma ? (
              <span><strong>Cadastro de empresas: Conap Ferramentas.</strong> Nome, CNPJ e situação vêm do cadastro geral da plataforma (só leitura).
                Aqui ficam só o responsável e os tipos de documento.</span>
            ) : (
              <span><strong>Cadastro de empresas: local.</strong> As empresas são cadastradas aqui. Quando o Faturamento estiver no Conap Ferramentas,
                o cadastro passa a vir do cadastro geral (<code>EMPRESAS_FONTE=plataforma</code>).</span>
            )}
            <span className="text-[13px]">
              {r.controleFiscal ? <><strong>Controle Fiscal: configurado.</strong> Responsáveis e CNPJs podem ser trazidos de lá (só leitura, com prévia). </>
                : <><strong>Controle Fiscal: não configurado</strong> (<code>FOLHA_DATABASE_URL</code> no <code>.env</code>). </>}
              {r.provedorResponsaveis === "manual" ? "Responsáveis: troca manual aqui ou por planilha." : <>Responsáveis vêm de <strong>{r.provedorResponsaveis}</strong>; trocas feitas aqui ficam como &quot;Manual&quot;.</>}
            </span>
          </div>
          {r.controleFiscal ? <Link className="btn btn-sm shrink-0" href={rota("empresas/controle-fiscal")}>Sincronizar com o Controle Fiscal</Link> : null}
        </div>
      ) : null}

      {ref.dados && d ? (
        <BarraFiltros>
          <SeletorCarteira rotulo="Responsável" valor={d.carteira} usuarios={ref.dados.usuarios} eu={usuario} onChange={(v) => f.set({ carteira: v === "todos" ? null : v })} />
          <label className="campo min-w-[240px] flex-1">
            <span>Buscar</span>
            <input className="entrada" type="search" placeholder="Nome ou CNPJ" value={texto} onChange={(e) => setTexto(e.target.value)} />
          </label>
          <label className="flex min-h-[38px] cursor-pointer items-center gap-2 text-[14px]">
            <input type="checkbox" className="check" checked={inativas} onChange={(e) => f.set({ inativas: e.target.checked ? null : "0" })} /> Mostrar inativas
          </label>
          <label className="campo ml-auto min-w-[160px]" title="Ao trocar o responsável na tabela, a troca vale a partir desta competência. Meses anteriores continuam com quem cuidava na época.">
            <span>Trocas valem a partir de</span>
            <select className="entrada" value={inicio} onChange={(e) => setInicio(e.target.value)}>
              {d.competencias.map((c) => <option key={c.valor} value={c.valor}>{c.curta}</option>)}
            </select>
          </label>
        </BarraFiltros>
      ) : null}

      {lista.erro ? <CaixaErro mensagens={lista.erro.mensagens} onTentar={() => void lista.recarregar()} /> : null}
      {!d && lista.carregando ? <Carregando /> : null}
      {d && ref.dados ? <Tabela key={`${d.carteira}|${d.busca}|${d.inativas}`} d={d} usuarios={ref.dados.usuarios} inicio={inicio || d.inicioPadrao.valor} filtrado={!!busca || carteira !== "todos"} /> : null}
    </>
  );
}

function Tabela({ d, usuarios, inicio, filtrado }: { d: RespEmpresas; usuarios: Usuario[]; inicio: string; filtrado: boolean }) {
  const avisar = useAviso();
  const [linhas, setLinhas] = useState(d.empresas);
  const [ocupada, setOcupada] = useState<number | null>(null);
  const rotuloInicio = d.competencias.find((c) => c.valor === inicio)?.curta ?? inicio;

  const trocar = async (e: LinhaEmpresa, uid: number) => {
    setOcupada(e.id);
    try {
      const r = await api<{ alterado: boolean; empresa: LinhaEmpresa }>(`/empresas/${e.id}/responsavel`, "POST", { usuarioId: uid, inicio });
      setLinhas((ls) => ls.map((x) => (x.id === e.id ? { ...x, ...r.empresa } : x)));
      const nome = usuarios.find((u) => u.id === uid)?.nome ?? "";
      avisar(r.alterado ? `Responsável de ${e.nome}: ${nome} a partir de ${rotuloInicio}.` : `Nada mudou: ${nome} já era o responsável nessa competência.`);
    } catch (er) {
      avisar(er instanceof ErroApi ? er.mensagens.join(" ") : "Não foi possível trocar o responsável.", "erro");
    } finally { setOcupada(null); }
  };

  if (!linhas.length) {
    return (
      <div className="card vazio">
        Nenhuma empresa encontrada{filtrado ? " com esses filtros" : ""}.{" "}
        {d.fontePlataforma ? <Link className="underline" href={rota("empresas/plataforma")}>Trazer do Conap Ferramentas</Link>
          : <><Link className="underline" href={rota("empresas/editar")}>Cadastre uma empresa</Link> ou <Link className="underline" href={rota("importacao")}>importe a planilha</Link></>}.
      </div>
    );
  }
  return (
    <Grupo titulo={<span className="text-[14px] font-normal text-[var(--ink-2)]">{linhas.filter((e) => e.ativa).length} ativa(s) de {linhas.length} listada(s)</span>}>
      <div className="rolagem">
        <table className="tabela" aria-label="Empresas">
          <thead><tr>
            <th>Empresa</th><th>CNPJ</th><th>Responsável</th><th>Origem</th><th>Tipos usados</th><th>Ativa</th><th><span className="sr-only">Ações</span></th>
          </tr></thead>
          <tbody>
            {linhas.map((e) => (
              <tr key={e.id} className={e.ativa ? "" : "opacity-55"}>
                <td className="font-medium">{e.nome}</td>
                <td className="whitespace-nowrap tabular-nums text-[var(--ink-2)]">{e.cnpj ? e.cnpjFormatado : "—"}</td>
                <td>
                  <select className="entrada !min-h-[34px] min-w-[140px] !py-1" value={e.responsavel?.id ?? ""} disabled={ocupada === e.id}
                          aria-label={`Responsável de ${e.nome}`} onChange={(ev) => void trocar(e, Number(ev.target.value))}>
                    {!e.responsavel ? <option value="" disabled>—</option> : null}
                    {usuarios.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
                  </select>
                </td>
                <td>{e.origem ? <span className={`badge ${e.origem === "integracao" ? "badge-info" : e.origem === "planilha" ? "badge-ok" : ""}`}>{ROTULO_ORIGEM[e.origem] ?? e.origem}</span> : <span className="text-[var(--ink-3)]">—</span>}</td>
                <td>
                  <div className="flex max-w-[360px] flex-wrap gap-1">
                    {e.tipos.length ? e.tipos.map((t) => <TagTipo key={t.id} t={t} />) : <span className="font-medium text-[var(--warn)]">Nenhum tipo definido</span>}
                  </div>
                </td>
                <td>{e.ativa ? <span className="badge badge-ok">Sim</span> : <span className="badge">Não</span>}</td>
                <td className="text-right"><Link className="btn btn-sm" href={rota("empresas/editar", { id: e.id })} aria-label={`Editar ${e.nome}`}>Editar</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Grupo>
  );
}
