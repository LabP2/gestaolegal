/** NPJ (tenant) como a API da plataforma devolve. */
export interface Tenant {
	id: number;
	nome: string;
	sigla: string;
	/** Identificador para CLI e scripts; não muda depois de criado. */
	slug: string;
	instituicao: string | null;
	ativo: boolean;
	criado_em: string;
	id_criado_por: number | null;
}

/** Administrador da plataforma (sem senha). */
export interface PlataformaAdmin {
	id: number;
	nome: string;
	email: string;
	ativo: boolean;
	criado_em: string;
	ultimo_login_em: string | null;
}

/** Corpo de `POST /api/plataforma/tenants`. */
export interface TenantCriacaoInput {
	nome: string;
	sigla: string;
	slug: string;
	instituicao?: string | null;
	unidade_nome: string;
	unidade_sigla: string;
	admin_nome: string;
	admin_email: string;
}

/** Corpo de `PUT /api/plataforma/tenants/<id>`. O slug não entra. */
export interface TenantEdicaoInput {
	nome?: string;
	sigla?: string;
	instituicao?: string | null;
}

/** Resposta da criação: o link de primeiro acesso é mostrado na tela (D10). */
export interface TenantCriado {
	tenant: Tenant;
	admin: { id: number; nome: string; email: string };
	link_primeiro_acesso: string;
}
