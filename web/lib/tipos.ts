/* Formato das respostas da API (/api/faturamento), em camelCase. Valores monetários vêm como texto. */

export type Id = number;
export type Dinheiro = string; // "1234.56"

export interface Usuario { id: Id; nome: string }

export interface Competencia { valor: string; curta: string; extenso: string; rotulo: string }

export type Status = "pendente" | "preenchido" | "sem_movimento";
export type Sentido = "E" | "S" | "O";

export interface Sessao {
  usuario: Usuario | null;
  modoAuth: "local" | "plataforma";
  usuarios: Usuario[];
  versao: string;
  recursos: { cruzamento: boolean; controleFiscal: boolean; empresasFonte: "local" | "plataforma"; provedorResponsaveis: string };
}

export interface TipoDocumento {
  id: Id; codigo: string; nome: string; modelo: string; sentido: Sentido; sentidoNome: string; ordem: number; ativo: boolean;
  uso?: { empresas: number; lancamentos: number } | null;
}

export interface Referencias {
  competencia: Competencia;
  competenciaPadrao: string;
  competenciaAtual: string;
  competencias: Competencia[];
  usuarios: Usuario[];
  tipos: TipoDocumento[];
  motivosAjuste: string[];
  sentidos: { valor: Sentido; nome: string; titulo: string }[];
  status: { valor: Status; rotulo: string }[];
  usuario: Usuario;
}

export interface EmpresaResumo { id: Id; nome: string; cnpj: string | null; cnpjFormatado: string; ativa: boolean }

export interface Ajuste {
  id: Id; grupo: "AUTOR" | "CANC"; qtde: number; valor: Dinheiro; motivo: string; observacao: string;
  criadoPor: Usuario | null; criadoEm: string;
}

export interface Linha {
  tipo: TipoDocumento;
  id: Id | null;
  qtdeAutor: number | null; valorAutor: Dinheiro | null; qtdeCanc: number | null; valorCanc: Dinheiro | null;
  ajustes: Ajuste[];
  ajusteQtdeAutor: number; ajusteValorAutor: Dinheiro; ajusteQtdeCanc: number; ajusteValorCanc: Dinheiro;
  totalQtdeAutor: number; totalValorAutor: Dinheiro; totalQtdeCanc: number; totalValorCanc: Dinheiro;
  bateu: boolean; bateuPor: Usuario | null; temMovimento: boolean; dicaAjuste: string; ajusteCurto: string;
}

export const ROTULO_STATUS: Record<Status, string> = { pendente: "Pendente", preenchido: "Preenchido", sem_movimento: "Sem movimento" };
export const CLASSE_STATUS: Record<Status, string> = { pendente: "badge-warn", preenchido: "badge-ok", sem_movimento: "" };

export interface BlocoConferencia {
  sentido: Sentido; titulo: string; nomeSubtotal: string;
  subtotal: { qtdeAutor: number; valorAutor: Dinheiro; qtdeCanc: number; valorCanc: Dinheiro };
  linhas: Linha[];
}
export interface CartaoConferencia {
  empresa: EmpresaResumo; responsavel: string | null; podeEditar: boolean;
  total: number; bateram: number; faltam: number; tudoBateu: boolean; blocos: BlocoConferencia[];
}
export interface ProgressoConferencia { linhas: number; bateram: number; percentual: number; empresasOk: number; empresasPendentes: number }
export interface RespConferencia {
  competencia: Competencia; carteira: string; nomeCarteira: string; vista: "todas" | "pendencia"; somenteLeitura: boolean;
  progresso: ProgressoConferencia; opcoes: { id: Id; nome: string }[]; escolhidas: Id[]; haLancamentos: boolean;
  geradoEm: string; cartoes: CartaoConferencia[];
}

export const ROTULO_ORIGEM: Record<string, string> = { manual: "Manual", planilha: "Planilha", integracao: "Integração" };
export const CLASSE_SENTIDO: Record<string, string> = { E: "badge-info", S: "badge-brand", O: "" };
