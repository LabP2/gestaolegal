import type { User } from './user';

export type OrigemEvento = 'manual' | 'djen';

export interface ArquivoEvento {
	id: number;
	nome: string;
	indisponivel_origem: boolean;
}

export interface Evento {
	id: number;
	id_caso: number;
	num_evento?: number;
	tipo: string;
	descricao?: string;
	arquivos: ArquivoEvento[];
	data_evento: string;
	data_criacao: string;
	/** Nulo só em evento criado pela rotina do DJEN. */
	id_criado_por: number | null;
	criado_por?: User | null;
	id_usuario_responsavel?: number;
	usuario_responsavel?: User;
	status: boolean;
	/** `djen`: veio de uma publicação; tipo, data e descrição não são editáveis. */
	origem: OrigemEvento;
	id_djen_comunicacao?: number | null;
	/** Falso = a publicação de origem foi cancelada no DJEN. */
	djen_ativa?: boolean | null;
}

export interface ListEvento {
	id: number;
	num_evento?: number;
	tipo: string;
	data_evento: string;
	data_criacao: string;
	criado_por?: string;
	id_criado_por?: number;
	descricao?: string;
	usuario_responsavel?: string;
	status: boolean;
	origem: OrigemEvento;
	id_djen_comunicacao?: number | null;
	djen_ativa?: boolean | null;
}

export interface EventoCreateInput {
	id_caso: number;
	num_evento?: number;
	tipo: string;
	descricao?: string;
	arquivos?: File[];
	data_evento: string;
	id_usuario_responsavel?: number;
	status?: boolean;
}

export interface EventoUpdateInput {
	id_caso?: number;
	num_evento?: number;
	tipo?: string;
	descricao?: string;
	arquivos?: File[];
	data_evento?: string;
	id_usuario_responsavel?: number;
	status?: boolean;
}
