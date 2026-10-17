"use client";
/* Cadastro geral de empresas do Conap Ferramentas (só leitura): compara com o cadastro daqui e aplica
   vínculos, nome/CNPJ/situação e, se pedido, cria as empresas que só existem lá. */
import Link from "next/link";
import { useState } from "react";
import { useAviso } from "@/components/Avisos";
import { Icone } from "@/components/Icone";
import { useSessao } from "@/components/Sessao";
import { Cabecalho, CaixaErro, ListaRelatorio, Metrica } from "@/components/ui";
import { api, ErroApi } from "@/lib/api";
import { rota } from "@/lib/usar";

interface Relatorio {
  vinculadas: string[]; casadasPeloNome: string[]; atualizadas: string[]; novas: string[]; criadas: string[]; soAqui: string[];
  semMudanca: number; lidas: number; erros: string[];
}

export function Plataforma() {
  const { sessao, usuario } = useSessao();
  const avisar = useAviso();
  const [criarNovas, setCriarNovas] = useState(false);
  const [resp, setResp] = useState<number>(usuario?.id ?? 0);
  const [rel, setRel] = useState<Relatorio | null>(null);
  const [erro, setErro] = useState<string[] | null>(null);
  const [enviando, setEnviando] = useState(false);
  const ligado = sessao?.recursos.empresasFonte === "plataforma";

  const chamar = async (aplicar: boolean) => {
    setEnviando(true); setErro(null);
    try {
      const r = await api<{ aplicado: boolean; relatorio: Relatorio }>("/empresas/plataforma/sincronizar", "POST", { aplicar, criarNovas, responsavelId: resp });
      if (r.aplicado) {
        avisar(`Cadastro aplicado: ${r.relatorio.vinculadas.length} vínculo(s), ${r.relatorio.atualizadas.length} atualização(ões), ${r.relatorio.criadas.length} criada(s).`);
        setRel(null);
      } else setRel(r.relatorio);
    } catch (e) { setErro(e instanceof ErroApi ? e.mensagens : [String(e)]); }
    finally { setEnviando(false); }
  };
  const temMudanca = !!rel && (rel.vinculadas.length + rel.atualizadas.length + (criarNovas ? rel.novas.length : 0)) > 0;

  return (
    <>
      <Cabecalho sobre={<Link href={rota("empresas")} className="hover:underline">Empresas</Link>} titulo="Cadastro de empresas do Conap Ferramentas"
                 descricao="O cadastro geral (vindo dos clientes da Domínio) é só lido. Aqui ficam o responsável e os tipos de documento de cada empresa." />
      {!ligado ? (
        <div className="aviso aviso-info" role="note">
          <Icone nome="info" className="mt-0.5 shrink-0 text-[var(--info)]" />
          <div>
            <strong>Hoje o cadastro de empresas é local</strong> (feito aqui no Faturamento). Para usar o cadastro geral do Conap Ferramentas, configure no{" "}
            <code>.env</code>: <code>EMPRESAS_FONTE=plataforma</code>, <code>PLATAFORMA_DATABASE_URL</code> (acesso só de leitura ao PostgreSQL da plataforma) e,
            se precisar, <code>PLATAFORMA_EMPRESAS_TABELA</code> / <code>PLATAFORMA_EMPRESAS_COLUNAS</code> com o nome da tabela e das colunas.
            Dá para ver a prévia mesmo assim, se o acesso ao banco estiver configurado.
          </div>
        </div>
      ) : null}

      <section className="card flex flex-wrap items-end gap-4 p-4">
        <label className="flex min-h-[38px] cursor-pointer items-center gap-2 text-[14px]">
          <input type="checkbox" className="check" checked={criarNovas} onChange={(e) => setCriarNovas(e.target.checked)} />
          Criar aqui as empresas que só existem no Conap Ferramentas
        </label>
        {criarNovas && sessao ? (
          <label className="campo"><span>Responsável das empresas novas</span>
            <select className="entrada" value={resp} onChange={(e) => setResp(Number(e.target.value))}>
              {sessao.usuarios.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
            </select></label>
        ) : null}
        <button className="btn btn-solid ml-auto" type="button" disabled={enviando} onClick={() => void chamar(false)}>{enviando && !rel ? "Lendo…" : "Ver prévia"}</button>
      </section>

      {erro ? <CaixaErro mensagens={erro} /> : null}

      {rel ? (
        <section className="card flex flex-col gap-4 p-5" aria-label="Prévia">
          <span className="text-[13px] text-[var(--ink-3)]">Prévia · nada foi alterado ainda · {rel.lidas} empresa(s) lida(s) no Conap Ferramentas</span>
          {rel.erros.length ? <CaixaErro mensagens={rel.erros} /> : (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Metrica rotulo="Serão vinculadas" valor={rel.vinculadas.length} tom="brand" />
                <Metrica rotulo="Dados atualizados" valor={rel.atualizadas.length} />
                <Metrica rotulo={criarNovas ? "Serão criadas" : "Só lá (não criadas)"} valor={rel.novas.length} tom={rel.novas.length && !criarNovas ? "warn" : undefined} />
                <Metrica rotulo="Só aqui" valor={rel.soAqui.length} tom={rel.soAqui.length ? "warn" : undefined} />
              </div>
              <ListaRelatorio titulo="Vínculos (por CNPJ ou nome)" itens={rel.vinculadas} />
              <ListaRelatorio titulo="Ligadas só pelo nome — confira" tom="warn" itens={rel.casadasPeloNome} />
              <ListaRelatorio titulo="Nome, CNPJ ou situação trazidos de lá" itens={rel.atualizadas} />
              <ListaRelatorio titulo={criarNovas ? "Empresas que serão criadas" : "Existem lá e não aqui"} itens={rel.novas} />
              <ListaRelatorio titulo="Existem aqui e não no Conap Ferramentas (nada muda)" itens={rel.soAqui} />
              {temMudanca ? (
                <div className="flex justify-end gap-2">
                  <button className="btn" type="button" onClick={() => setRel(null)}>Cancelar</button>
                  <button className="btn btn-solid" type="button" disabled={enviando} onClick={() => void chamar(true)}>Aplicar</button>
                </div>
              ) : <div className="aviso aviso-info">Nada a aplicar: o cadastro daqui já está igual ao do Conap Ferramentas ({rel.semMudanca} sem mudança).</div>}
            </>
          )}
        </section>
      ) : null}
    </>
  );
}
