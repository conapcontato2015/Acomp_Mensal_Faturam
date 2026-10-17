"use client";
/* Sincronizar responsáveis/CNPJ/código com o Controle Fiscal (banco de lá só lido): prévia e aplicar. */
import Link from "next/link";
import { useState } from "react";
import { useAviso } from "@/components/Avisos";
import { Icone } from "@/components/Icone";
import { Cabecalho, CaixaErro, Carregando, ListaRelatorio, Metrica } from "@/components/ui";
import { api, ErroApi } from "@/lib/api";
import type { Competencia } from "@/lib/tipos";
import { rota, useDados } from "@/lib/usar";

interface Relatorio {
  trocas: string[]; semMudanca: number; cnpjsPreenchidos: string[]; codigosVinculados: string[]; cnpjDivergente: string[];
  ativaDivergente: string[]; casadasPeloNome: string[]; repetidas: string[]; naoEncontradas: string[]; semResponsavelLa: string[];
  responsaveisSemCorrespondencia: string[]; soNoControleFiscal: number; lidas: number; erros: string[]; divergencias: number; temAlteracoes: boolean;
}
interface RespInfo { configurado: boolean; inicioPadrao: Competencia; competencias: Competencia[] }
interface RespSinc { aplicado: boolean; inicio: Competencia; relatorio: Relatorio }

export function ControleFiscal() {
  const info = useDados<RespInfo>("/controle-fiscal");
  const avisar = useAviso();
  const [inicio, setInicio] = useState("");
  const [res, setRes] = useState<RespSinc | null>(null);
  const [erro, setErro] = useState<string[] | null>(null);
  const [enviando, setEnviando] = useState(false);
  const d = info.dados;
  if (info.erro) return <CaixaErro mensagens={info.erro.mensagens} />;
  if (!d) return <Carregando />;
  const ini = inicio || d.inicioPadrao.valor;

  const chamar = async (aplicar: boolean) => {
    setEnviando(true); setErro(null);
    try {
      const r = await api<RespSinc>("/controle-fiscal", "POST", { inicio: ini, aplicar });
      if (r.aplicado) { avisar("Controle Fiscal aplicado."); setRes(null); } else setRes(r);
    } catch (e) { setErro(e instanceof ErroApi ? e.mensagens : [String(e)]); }
    finally { setEnviando(false); }
  };
  const rel = res?.relatorio;

  return (
    <>
      <Cabecalho sobre={<Link href={rota("empresas")} className="hover:underline">Empresas</Link>} titulo="Sincronizar com o Controle Fiscal" />
      {!d.configurado ? (
        <div className="aviso aviso-danger" role="alert">
          <Icone nome="alerta" className="mt-0.5 shrink-0 text-[var(--danger)]" />
          <div><strong>Controle Fiscal: não configurado.</strong> Coloque no arquivo <code>.env</code> do Faturamento a linha{" "}
            <code>FOLHA_DATABASE_URL=postgresql://usuario:senha@localhost:5432/controle_fiscal</code> e reinicie o Faturamento.
            Se algum responsável tiver nome diferente nos dois sistemas, use também <code>FOLHA_MAPA_RESPONSAVEIS=NomeLa=NomeAqui;Outro=Natan</code>.</div>
        </div>
      ) : (
        <>
          <div className="aviso aviso-info" role="note">
            <Icone nome="info" className="mt-0.5 shrink-0 text-[var(--info)]" />
            <span>O banco do Controle Fiscal é <strong>só lido</strong> — nada é alterado lá. Aqui mudam apenas: o responsável (a partir da competência
              escolhida, com origem &quot;Integração&quot;), o CNPJ quando estiver vazio e o código do Controle Fiscal. Situação e &quot;sem movimento&quot; não são
              alterados; diferenças só aparecem na lista para você conferir.</span>
          </div>
          <section className="card flex flex-wrap items-end gap-3 p-4">
            <label className="campo"><span>Trocas valem a partir de</span>
              <select className="entrada" value={ini} onChange={(e) => { setInicio(e.target.value); setRes(null); }}>
                {d.competencias.map((c) => <option key={c.valor} value={c.valor}>{c.curta}</option>)}
              </select></label>
            <button className="btn btn-solid" type="button" disabled={enviando} onClick={() => void chamar(false)}>{enviando && !res ? "Lendo…" : "Ver prévia"}</button>
          </section>
        </>
      )}

      {erro ? <CaixaErro mensagens={erro} /> : null}

      {res && rel ? (
        <section className="card flex flex-col gap-4 p-5" aria-label="Prévia">
          <div><span className="text-[13px] text-[var(--ink-3)]">Prévia · nada foi alterado ainda</span>
            <h2 className="text-[16px] font-semibold">Controle Fiscal → Faturamento, trocas a partir de {res.inicio.curta}</h2></div>
          {rel.erros.length ? <CaixaErro mensagens={["Não foi possível ler o Controle Fiscal.", ...rel.erros]} /> : (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Metrica rotulo="Responsáveis que mudam" valor={rel.trocas.length} tom="brand" />
                <Metrica rotulo="CNPJs a preencher" valor={rel.cnpjsPreenchidos.length} />
                <Metrica rotulo="Divergências" valor={rel.divergencias} tom={rel.divergencias ? "warn" : undefined} />
                <Metrica rotulo="Não encontradas lá" valor={rel.naoEncontradas.length} tom={rel.naoEncontradas.length ? "warn" : undefined} />
              </div>
              <p className="text-[13px] text-[var(--ink-3)]">
                {rel.lidas} empresa(s) lida(s) no Controle Fiscal · {rel.semMudanca} já com o mesmo responsável
                {rel.codigosVinculados.length ? ` · ${rel.codigosVinculados.length} código(s) do Controle Fiscal a vincular` : ""}
                {rel.soNoControleFiscal ? ` · ${rel.soNoControleFiscal} empresa(s) do Controle Fiscal não estão no Faturamento (não são criadas aqui)` : ""}
              </p>
              <ListaRelatorio titulo="Responsáveis que mudam (de → para)" itens={rel.trocas} />
              <ListaRelatorio titulo="CNPJs que serão preenchidos" itens={rel.cnpjsPreenchidos} />
              <ListaRelatorio titulo="Divergências — nada disso é alterado automaticamente" tom="warn"
                              itens={[...rel.cnpjDivergente.map((i) => `CNPJ diferente — ${i}`), ...rel.ativaDivergente, ...rel.casadasPeloNome, ...rel.repetidas]} />
              <ListaRelatorio titulo="Empresas do Faturamento não encontradas no Controle Fiscal" itens={rel.naoEncontradas} />
              <ListaRelatorio titulo="Sem responsável no Controle Fiscal (nada muda)" itens={rel.semResponsavelLa} />
              <ListaRelatorio titulo="Nomes de responsáveis sem correspondência aqui" itens={rel.responsaveisSemCorrespondencia}>
                <p className="text-[13px] text-[var(--ink-3)]">Se for a mesma pessoa com outro nome, configure <code>FOLHA_MAPA_RESPONSAVEIS=NomeLa=NomeAqui</code> no <code>.env</code>.</p>
              </ListaRelatorio>
              {rel.temAlteracoes ? (
                <div className="flex flex-col items-end gap-1">
                  <div className="flex gap-2">
                    <Link className="btn" href={rota("empresas")}>Cancelar</Link>
                    <button className="btn btn-solid" type="button" disabled={enviando} onClick={() => void chamar(true)}>Aplicar</button>
                  </div>
                  <span className="text-[13px] text-[var(--ink-3)]">Ao aplicar, o Controle Fiscal é lido de novo: vale o que estiver lá nesse momento.</span>
                </div>
              ) : <div className="aviso aviso-info">Nada a aplicar: o Faturamento já está igual ao Controle Fiscal.</div>}
            </>
          )}
        </section>
      ) : null}
    </>
  );
}
