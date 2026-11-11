import type { Endereco } from './endereco';

export interface ListAtendido {
	id: number;
	nome: string;
	/** Nulos só na parte cadastrada sem triagem (`sem_triagem`). */
	cpf: string | null;
	telefone: string | null;
	celular: string | null;
	email: string | null;
	data_nascimento: string | null;
	status: boolean;
	/** Tem ficha de assistido ou foi cadastrado sem triagem. */
	is_assistido: boolean;
	sem_triagem: boolean;
	endereco: Endereco | null;
}

export interface Atendido {
	id: number;
	nome: string;
	// Os dados pessoais vêm nulos na parte cadastrada sem triagem.
	cpf?: string | null;
	cnpj?: string | null;
	email?: string | null;
	telefone?: string | null;
	celular?: string | null;
	data_nascimento?: string | null;
	estado_civil?: string | null;
	logradouro?: string;
	numero?: string;
	complemento?: string;
	bairro?: string;
	cep?: string;
	cidade?: string;
	estado?: string;
	como_conheceu?: string | null;
	indicacao_orgao?: string | null;
	procurou_outro_local?: string | null;
	procurou_qual_local?: string | null;
	obs?: string | null;
	pj_constituida?: string | null;
	repres_legal?: boolean | null;
	nome_repres_legal?: string | null;
	cpf_repres_legal?: string | null;
	contato_repres_legal?: string | null;
	rg_repres_legal?: string | null;
	nascimento_repres_legal?: string | null;
	status?: number;
	/** Parte cadastrada sem triagem (processo sem caso): conta como assistido. */
	sem_triagem?: boolean;
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

/** Variação do nome para a busca no DJEN (`GET /api/atendido/<id>/nomes`). */
export interface AtendidoNome {
	id: number;
	nome: string;
}

/** Corpo de `POST /api/atendido/simplificado`. */
export interface AtendidoSimplificadoInput {
	nome: string;
	cpf?: string | null;
	cnpj?: string | null;
	obs?: string | null;
}
