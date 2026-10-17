"use client";
/* Cadastro de uma empresa (nova ou ?id=): nome, CNPJ, situação, responsável (com início) e tipos usados.
   Com o cadastro vindo do Conap Ferramentas, nome/CNPJ/situação ficam só para leitura. */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAviso } from "@/components/Avisos";
import { useSessao } from "@/components/Sessao";
import { Cabecalho, CaixaErro, Carregando, Grupo, TagTipo } from "@/components/ui";
import { api, ErroApi } from "@/lib/api";
import { data, dataHora } from "@/lib/formato";
import type { Competencia, EmpresaResumo, Sentido, TipoDocumento, Usuario } from "@/lib/tipos";
import { ROTULO_ORIGEM } from "@/lib/tipos";
import { rota, useDados, useFiltros } from "@/lib/usar";

interface Vinculo { usuario: Usuario | null; inicio: Competencia; desdeOInicio: boolean; origem: string; registradoPor: Usuario | null; registradoEm: string }
interface RespEmpresa {
  empresa: EmpresaResumo & { externalId: string | null; responsavel: Usuario | null; tipos: number[] };
  historicoResponsaveis: Vinculo[];
  historico: { id: number; data: string; usuario: string | null; descricao: string }[];
  inicioPadrao: Competencia; competencias: Competencia[]; fontePlataforma: boolean;
}
interface RespTipos { tipos: TipoDocumento[]; sentidos: { valor: Sentido; nome: string; titulo: string }[] }
interface RespCompetencias { inicioPadrao: Competencia; competencias: Competencia[] }

export function EmpresaForm() {
  const f = useFiltros();
  const id = f.get("id");
  const { sessao } = useSessao();
  const emp = useDados<RespEmpresa>(id ? `/empresas/${id}` : null);
  const tipos = useDados<RespTipos>("/tipos-documento");
  const comps = useDados<RespCompetencias>(id ? null : "/responsaveis");
  const erro = emp.erro ?? tipos.erro ?? comps.erro;
  if (erro) return <><Cabecalho titulo="Empresa" /><CaixaErro mensagens={erro.mensagens} /><Link className="btn self-start" href={rota("empresas")}>Voltar para Empresas</Link></>;
  const base = id ? emp.dados : comps.dados;
  if (!tipos.dados || !sessao || !base) return <Carregando />;
  const plataforma = emp.dados?.fontePlataforma ?? sessao.recursos.empresasFonte === "plataforma";
  if (!id && plataforma) {
    return (
      <>
        <Cabecalho sobre={<Link href={rota("empresas")} className="hover:underline">Empresas</Link>} titulo="Nova empresa" />
        <div className="aviso aviso-info">Empresas novas vêm do cadastro geral do Conap Ferramentas. <Link className="underline" href={rota("empresas/plataforma")}>Trazer do Conap Ferramentas</Link>.</div>
      </>
    );
  }
  return <Formulario key={id || "nova"} d={emp.dados} tipos={tipos.dados} usuarios={sessao.usuarios}
                     inicioPadrao={base.inicioPadrao} competencias={base.competencias} plataforma={plataforma} />;
}

function Formulario({ d, tipos, usuarios, inicioPadrao, competencias, plataforma }: {
  d: RespEmpresa | null; tipos: RespTipos; usuarios: Usuario[]; inicioPadrao: Competencia; competencias: Competencia[]; plataforma: boolean;
}) {
  const router = useRouter();
  const avisar = useAviso();
  const { usuario } = useSessao();
  const e = d?.empresa;
  const respOriginal = e?.responsavel?.id ?? usuario?.id ?? usuarios[0]?.id ?? 0;
  const [nome, setNome] = useState(e?.nome ?? "");
  const [cnpj, setCnpj] = useState(e?.cnpjFormatado || "");
  const [ativa, setAtiva] = useState(e?.ativa ?? true);
  const [marcados, setMarcados] = useState<Set<number>>(new Set(e?.tipos ?? []));
  const [resp, setResp] = useState<number>(respOriginal);
  const [inicio, setInicio] = useState(inicioPadrao.valor);
  const [erros, setErros] = useState<string[] | null>(null);
  const [salvando, setSalvando] = useState(false);
  const travado = plataforma; // nome, CNPJ e situação vêm do cadastro geral

  const alternar = (tid: number) => setMarcados((m) => { const n = new Set(m); if (n.has(tid)) n.delete(tid); else n.add(tid); return n; });

  const salvar = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setSalvando(true);
    setErros(null);
    const tiposIds = [...marcados];
    try {
      if (!e) {
        const r = await api<{ empresa: EmpresaResumo }>("/empresas", "POST", { nome, cnpj, ativa, tipos: tiposIds, responsavelId: resp });
        avisar(`Empresa ${r.empresa.nome} cadastrada.`);
        router.push(rota("empresas"));
      } else {
        // Responsável só é mexido se a pessoa ou o início mudaram.
        const mudouResp = resp !== respOriginal || inicio !== inicioPadrao.valor;
        const corpo: Record<string, unknown> = { tipos: tiposIds };
        if (!travado) Object.assign(corpo, { nome, cnpj, ativa });
        if (mudouResp) Object.assign(corpo, { responsavelId: resp, inicio });
        const r = await api<{ responsavelAlterado: boolean }>(`/empresas/${e.id}`, "PUT", corpo);
        avisar(`Salvo.${r.responsavelAlterado ? " Responsável alterado." : ""}`);
        router.push(rota("empresas"));
      }
    } catch (er) {
      setErros(er instanceof ErroApi ? er.mensagens : [String(er)]);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } finally { setSalvando(false); }
  };

  return (
    <>
      <Cabecalho sobre={<Link href={rota("empresas")} className="hover:underline">Empresas</Link>}
                 titulo={e ? e.nome : "Nova empresa"} descricao="Cadastro, responsável da carteira e tipos de documento usados no lançamento." />
      {erros ? <CaixaErro mensagens={erros} /> : null}

      <form className="card flex max-w-[820px] flex-col gap-5 p-5" onSubmit={(ev) => void salvar(ev)} autoComplete="off">
        {travado ? (
          <div className="aviso aviso-info text-[13px]">Nome, CNPJ e situação vêm do cadastro geral do Conap Ferramentas{e?.externalId ? ` (${e.externalId})` : ""}: altere por lá.</div>
        ) : null}
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="campo"><span>Nome de exibição</span>
            <input className="entrada" required maxLength={160} value={nome} readOnly={travado} onChange={(x) => setNome(x.target.value)} /></label>
          <label className="campo"><span>CNPJ (chave para ligar com a plataforma)</span>
            <input className="entrada tabular-nums" inputMode="numeric" placeholder="00.000.000/0000-00" value={cnpj} readOnly={travado} onChange={(x) => setCnpj(x.target.value)} /></label>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-[14px]">
          <input type="checkbox" className="check" checked={ativa} disabled={travado} onChange={(x) => setAtiva(x.target.checked)} />
          Empresa ativa (inativas não aparecem no painel nem no lançamento)
        </label>

        <fieldset className="flex flex-col gap-3 rounded-xl border border-[var(--line)] px-4 pb-4 pt-2">
          <legend className="px-1.5 font-semibold">Responsável da carteira</legend>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="campo"><span>Responsável</span>
              <select className="entrada" value={resp} onChange={(x) => setResp(Number(x.target.value))}>
                {usuarios.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
              </select></label>
            {e ? (
              <label className="campo"><span>Vale a partir da competência</span>
                <select className="entrada" value={inicio} onChange={(x) => setInicio(x.target.value)}>
                  {competencias.map((c) => <option key={c.valor} value={c.valor}>{c.curta}</option>)}
                </select></label>
            ) : null}
          </div>
          {e && d ? (
            <>
              <span className="text-[13px] text-[var(--ink-3)]">Meses anteriores continuam no resumo de quem cuidava na época.</span>
              <div className="flex flex-col gap-1.5">
                <span className="text-[13px] font-medium text-[var(--ink-2)]">Histórico de responsáveis</span>
                {d.historicoResponsaveis.length ? (
                  <ul className="flex list-disc flex-col gap-1 pl-5 text-[14px]">
                    {d.historicoResponsaveis.map((v, i) => (
                      <li key={i}>
                        <strong>{v.usuario?.nome ?? "—"}</strong> {v.desdeOInicio ? "desde o início" : `a partir de ${v.inicio.curta}`}
                        <span className="text-[13px] text-[var(--ink-3)]"> · {ROTULO_ORIGEM[v.origem] ?? v.origem}{v.registradoPor ? ` · por ${v.registradoPor.nome}` : ""} · {data(v.registradoEm)}</span>
                        {i === 0 ? <span className="badge badge-ok ml-2">atual</span> : null}
                      </li>
                    ))}
                  </ul>
                ) : <span className="text-[13px] text-[var(--ink-3)]">Sem responsável registrado.</span>}
              </div>
            </>
          ) : <span className="text-[13px] text-[var(--ink-3)]">Na criação, o responsável vale para todos os meses. Trocas depois ficam no histórico.</span>}
        </fieldset>

        <fieldset className="flex flex-col gap-3 rounded-xl border border-[var(--line)] px-4 pb-4 pt-2">
          <legend className="px-1.5 font-semibold">Tipos de documento usados</legend>
          <span className="text-[13px] text-[var(--ink-3)]">
            Só os tipos marcados aparecem no lançamento. Entradas e saídas nunca se somam; &quot;Outros&quot; fica fora dos dois totais.
            Precisa de um tipo novo? <Link className="underline" href={rota("tipos-documento")}>Cadastrar tipos de documento</Link>.
          </span>
          <div className="grid gap-4 sm:grid-cols-3">
            {tipos.sentidos.map((s) => (
              <div key={s.valor} role="group" aria-label={s.titulo} className="flex flex-col gap-2">
                <span className="text-[12px] font-semibold uppercase tracking-[.05em] text-[var(--ink-3)]">{s.titulo}</span>
                {tipos.tipos.filter((t) => t.sentido === s.valor).map((t) => (
                  <label key={t.id} className="flex cursor-pointer items-center gap-2 text-[14px]">
                    <input type="checkbox" className="check" checked={marcados.has(t.id)} onChange={() => alternar(t.id)} aria-label={t.nome} />
                    <TagTipo t={t} />
                  </label>
                ))}
                {!tipos.tipos.some((t) => t.sentido === s.valor) ? <span className="text-[13px] text-[var(--ink-3)]">Nenhum tipo ativo.</span> : null}
              </div>
            ))}
          </div>
        </fieldset>

        <div className="flex justify-end gap-2">
          <Link className="btn" href={rota("empresas")}>Cancelar</Link>
          <button className="btn btn-solid" type="submit" disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
        </div>
      </form>

      {d ? (
        <Grupo className="max-w-[820px]" titulo="Histórico" acoes={<Link className="btn btn-quiet btn-sm" href={rota("historico", { empresa: d.empresa.id })}>Ver tudo</Link>}>
          {d.historico.length ? (
            <div className="rolagem">
              <table className="tabela">
                <thead><tr><th>Data</th><th>Usuário</th><th>O que mudou</th></tr></thead>
                <tbody>
                  {d.historico.map((h) => (
                    <tr key={h.id}>
                      <td className="whitespace-nowrap text-[var(--ink-3)] tabular-nums">{dataHora(h.data)}</td>
                      <td>{h.usuario ?? "—"}</td>
                      <td>{h.descricao}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="vazio">Nenhuma alteração registrada.</div>}
        </Grupo>
      ) : null}
    </>
  );
}
