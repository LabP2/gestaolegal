import type { Endereco } from './endereco';

export interface ListAtendido {
	id: number;
	nome: string;
	cpf: string;
	telefone: string;
	celular: string;
	email: string;
	data_nascimento: string;
	status: boolean;
	is_assistido: boolean;
	endereco: Endereco;
}

export interface Atendido {
	id: number;
	nome: string;
	cpf?: string;
	cnpj?: string;
	email?: string;
	telefone?: string;
	celular?: string;
	data_nascimento?: string;
	estado_civil?: string;
	logradouro?: string;
	numero?: string;
	complemento?: string;
	bairro?: string;
	cep?: string;
	cidade?: string;
	estado?: string;
	como_conheceu?: string;
	indicacao_orgao?: string;
	procurou_outro_local?: string;
	procurou_qual_local?: string;
	obs?: string;
	pj_constituida?: string;
	repres_legal?: boolean | null;
	nome_repres_legal?: string | null;
	cpf_repres_legal?: string | null;
	contato_repres_legal?: string | null;
	rg_repres_legal?: string | null;
	nascimento_repres_legal?: string | null;
	pretende_constituir_pj?: string | null;
	status?: number;
	created_at?: string;
	updated_at?: string;
	// The API returns the address as a nested object; the flat fields above are
	// used by the create/edit form schema.
	endereco?: Endereco;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	assistido?: {
		assistido_pessoa_juridica?: AssistidoPessoaJuridica | null;
		[key: string]: any;
	};
}

export interface AssistidoPessoaJuridica {
	enquadramento: 'mei' | 'microempresa' | 'pequeno_porte' | 'outros';
	especificacao_enquadramento?: string | null;
	socios: string[];
	situacao_receita?: 'Ativa' | 'Baixada' | 'Outras' | null;
}
