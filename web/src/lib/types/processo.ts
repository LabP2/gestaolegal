import type { User } from './user';

export interface Processo {
	id: number;
	especie: string;
	numero?: string | null;
	identificacao?: string;
	vara?: string;
	link?: string;
	probabilidade?: string;
	posicao_assistido?: string;
	valor_causa_inicial?: number;
	valor_causa_atual?: number;
	data_distribuicao?: string;
	data_transito_em_julgado?: string;
	obs?: string;
	/** Nulo no processo sem caso (docs/plano-processos-avulsos.md). */
	id_caso: number | null;
	unidade_id?: number;
	status: boolean;
	id_criado_por: number;
	criado_por?: User;
	/** DJEN: só os 20 dígitos do número, quando segue o padrão CNJ. */
	numero_cnj?: string | null;
	/** DJEN: aguardando a rotina buscar o histórico de publicações. */
	djen_pendente?: boolean;
	/** DJEN: última consulta das publicações do processo. */
	djen_consultado_em?: string | null;
}

export interface ListProcesso {
	id: number;
	especie: string;
	numero?: string | null;
	identificacao?: string;
	vara?: string;
	probabilidade?: string;
	posicao_assistido?: string;
	valor_causa_inicial?: number;
	valor_causa_atual?: number;
	data_distribuicao?: string;
	data_transito_em_julgado?: string;
	status: boolean;
	criado_por?: User;
}

export interface ProcessoCreateInput {
	especie: string;
	numero?: string | null;
	identificacao?: string;
	vara?: string;
	link?: string;
	probabilidade?: string;
	posicao_assistido?: string;
	valor_causa_inicial?: number;
	valor_causa_atual?: number;
	data_distribuicao?: string;
	data_transito_em_julgado?: string;
	obs?: string;
	id_caso: number;
	status?: boolean;
}

export interface ProcessoUpdateInput {
	especie?: string;
	numero?: string | null;
	identificacao?: string;
	vara?: string;
	link?: string;
	probabilidade?: string;
	posicao_assistido?: string;
	valor_causa_inicial?: number;
	valor_causa_atual?: number;
	data_distribuicao?: string;
	data_transito_em_julgado?: string;
	obs?: string;
	id_caso?: number;
	status?: boolean;
}

/** Papéis que veem e cadastram processos sem caso (mesma régua da lista do DJEN). */
export const PROCESSO_PAPEIS_SEM_CASO = ['admin', 'prof', 'orient', 'colab_proj'];

export type PoloParte = 'ativo' | 'passivo' | 'outro';

export const POLO_PARTE_LABEL: Record<PoloParte, string> = {
	ativo: 'Polo ativo',
	passivo: 'Polo passivo',
	outro: 'Outro'
};

/** Parte do processo: de `processo_partes` ou, no processo de caso, do caso. */
export interface ParteProcesso {
	id: number | null;
	id_atendido: number;
	nome: string;
	polo: PoloParte | null;
	sem_triagem: boolean;
	origem: 'processo' | 'caso';
}

/** `GET /api/processos/<id>`. */
export interface ProcessoDetalhe extends Processo {
	partes: ParteProcesso[];
	total_publicacoes: number;
}

/** Linha de `GET /api/processos`. */
export interface ProcessoListItem {
	id: number;
	especie: string;
	status: boolean;
	unidade_id: number;
	id_caso: number | null;
	numero: string | null;
	numero_cnj: string | null;
	identificacao: string | null;
	vara: string | null;
	data_distribuicao: string | null;
	partes: string[];
	total_publicacoes: number;
}

/** Paginação plana devolvida pela API (`PaginatedResult.to_dict`). */
export interface PaginaProcessos {
	items: ProcessoListItem[];
	total: number;
	page: number;
	per_page: number;
	total_pages: number;
	has_next_page: boolean;
	has_previous_page: boolean;
}

/** Corpo de `POST /api/processos` (processo sem caso). */
export interface ProcessoSemCasoInput extends Omit<ProcessoCreateInput, 'id_caso'> {
	partes: { id_atendido: number; polo?: PoloParte | null }[];
}
