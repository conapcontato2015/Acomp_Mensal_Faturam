"use client";
/* Tipos de documento: o que pode ser lançado em cada empresa. Tipo com lançamentos não muda de sentido
   e não é excluído (inative para parar de usar). */
import { useState } from "react";
import { useAviso } from "@/components/Avisos";
import { Cabecalho, CaixaErro, Carregando, Grupo, TagTipo } from "@/components/ui";
import { api, ErroApi } from "@/lib/api";
import type { Sentido, TipoDocumento } from "@/lib/tipos";
import { useDados } from "@/lib/usar";

interface RespTipos { tipos: (TipoDocumento & { uso: { empresas: number; lancamentos: number } })[]; sentidos: { valor: Sentido; nome: string; titulo: string }[] }

export function Tipos() {
  const lista = useDados<RespTipos>("/tipos-documento?todos=true");
  const avisar = useAviso();
  const [nome, setNome] = useState("");
  const [sentido, setSentido] = useState<Sentido>("E");
  const [erro, setErro] = useState<string[] | null>(null);
  const d = lista.dados;

  const criar = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setErro(null);
    try {
      const r = await api<{ tipo: TipoDocumento }>("/tipos-documento", "POST", { nome, sentido });
      avisar(`Tipo "${r.tipo.nome}" criado. Marque-o nas empresas que o usam.`);
      setNome("");
      await lista.recarregar();
    } catch (e) { setErro(e instanceof ErroApi ? e.mensagens : [String(e)]); }
  };

  return (
    <>
      <Cabecalho titulo="Tipos de documento" descricao={<>O que pode ser lançado em cada empresa. Entradas e saídas nunca se somam; &quot;Outros&quot; fica fora dos dois totais e do gráfico.</>} />
      <form className="card flex flex-wrap items-end gap-3 p-4" onSubmit={(e) => void criar(e)} autoComplete="off" aria-label="Novo tipo">
        <label className="campo min-w-[220px] flex-[2]"><span>Nome do novo tipo</span>
          <input className="entrada" required maxLength={60} placeholder="Ex.: SPED Entradas" value={nome} onChange={(e) => setNome(e.target.value)} /></label>
        <label className="campo min-w-[160px] flex-1"><span>Sentido</span>
          <select className="entrada" value={sentido} onChange={(e) => setSentido(e.target.value as Sentido)}>
            {(d?.sentidos ?? []).map((s) => <option key={s.valor} value={s.valor}>{s.nome}</option>)}
          </select></label>
        <button className="btn btn-solid" type="submit">Adicionar tipo</button>
      </form>
      {erro ? <CaixaErro mensagens={erro} /> : null}
      {lista.erro ? <CaixaErro mensagens={lista.erro.mensagens} onTentar={() => void lista.recarregar()} /> : null}
      {!d ? (lista.carregando ? <Carregando /> : null) : (
        <Grupo>
          <div className="rolagem">
            <table className="tabela" aria-label="Tipos de documento">
              <thead><tr><th>Nome</th><th>Sentido</th><th className="num">Ordem</th><th className="num">Empresas</th><th className="num">Lançamentos</th><th>Situação</th><th /></tr></thead>
              <tbody>
                {d.tipos.map((t) => <LinhaTipo key={`${t.id}-${t.nome}-${t.ordem}-${t.ativo}-${t.sentido}`} t={t} sentidos={d.sentidos} aoSalvar={() => void lista.recarregar()} />)}
              </tbody>
            </table>
          </div>
        </Grupo>
      )}
      <p className="text-[13px] text-[var(--ink-3)]">
        Tipo com lançamentos não muda de sentido (para não misturar entradas, saídas e outros nos totais) e não é excluído: inative para parar de usar.
        Depois de criar, marque o tipo nas empresas que o usam, em Empresas.
      </p>
    </>
  );
}

function LinhaTipo({ t, sentidos, aoSalvar }: { t: RespTipos["tipos"][number]; sentidos: RespTipos["sentidos"]; aoSalvar: () => void }) {
  const avisar = useAviso();
  const [nome, setNome] = useState(t.nome);
  const [sentido, setSentido] = useState<Sentido>(t.sentido);
  const [ordem, setOrdem] = useState(String(t.ordem));
  const [ativo, setAtivo] = useState(t.ativo);
  const [salvando, setSalvando] = useState(false);
  const mudou = nome !== t.nome || sentido !== t.sentido || ordem !== String(t.ordem) || ativo !== t.ativo;

  const salvar = async () => {
    setSalvando(true);
    try {
      await api(`/tipos-documento/${t.id}`, "PUT", { nome, sentido, ordem, ativo, modelo: t.modelo });
      avisar(`Tipo "${nome}" salvo.`);
      aoSalvar();
    } catch (e) { avisar(e instanceof ErroApi ? e.mensagens.join(" ") : String(e), "erro"); }
    finally { setSalvando(false); }
  };

  return (
    <tr className={t.ativo ? "" : "opacity-55"}>
      <td><input className="entrada min-w-[180px]" maxLength={60} value={nome} aria-label={`Nome de ${t.nome}`} onChange={(e) => setNome(e.target.value)} /></td>
      <td>
        {t.uso.lancamentos ? <span title="Tem lançamentos: o sentido não muda"><TagTipo t={{ nome: t.sentidoNome, sentido: t.sentido }} /></span> : (
          <select className="entrada min-w-[130px]" value={sentido} aria-label={`Sentido de ${t.nome}`} onChange={(e) => setSentido(e.target.value as Sentido)}>
            {sentidos.map((s) => <option key={s.valor} value={s.valor}>{s.nome}</option>)}
          </select>
        )}
      </td>
      <td className="num"><input className="entrada w-[76px] text-right" inputMode="numeric" value={ordem} aria-label={`Ordem de ${t.nome}`} onChange={(e) => setOrdem(e.target.value)} /></td>
      <td className="num">{t.uso.empresas}</td>
      <td className="num">{t.uso.lancamentos}</td>
      <td>
        <label className="flex cursor-pointer items-center gap-2"><input type="checkbox" className="check" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} /> Ativo</label>
      </td>
      <td className="text-right"><button className={`btn btn-sm ${mudou ? "btn-solid" : ""}`} type="button" disabled={!mudou || salvando} onClick={() => void salvar()}>Salvar</button></td>
    </tr>
  );
}
