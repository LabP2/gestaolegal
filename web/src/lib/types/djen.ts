/** Publicações do DJEN (docs/plano-djen.md, §5). Contrato: revisão humana. */

export type SituacaoPublicacao = 'vinculada' | 'pendente' | 'descartada';

export const SITUACAO_PUBLICACAO_LABEL: Record<SituacaoPublicacao, string> = {
	vinculada: 'Importado',
	pendente: 'Não analisado',
	descartada: 'Descartado'
};

/** Papéis que veem a caixa "Sem caso" e podem vincular ou descartar (§7). */
export const DJEN_PAPEIS_GESTAO = ['admin', 'prof', 'orient'];

/** Linha de `GET /api/djen/publicacoes`. */
export interface PublicacaoListItem {
	id: number;
	data_disponibilizacao: string;
	numero_processo: string;
	numero_processo_mascara: string | null;
	situacao: SituacaoPublicacao;
	/** Falso = publicação cancelada no DJEN. */
	ativo: boolean;
	sigla_tribunal: string | null;
	nome_orgao: string | null;
	tipo_comunicacao: string | null;
	tipo_documento: string | null;
	nome_classe: string | null;
	id_processo: number | null;
	id_caso: number | null;
	oab_origem: string | null;
	resumo: string | null;
}

export interface DestinatarioPublicacao {
	nome: string | null;
	/** A = ativo, P = passivo. */
	polo: string | null;
}

export interface AdvogadoPublicacao {
	nome: string | null;
	numero_oab: string | null;
	uf_oab: string | null;
}

/** `GET /api/djen/publicacoes/<id>`. O HTML original nunca vem: só o filtrado. */
export interface Publicacao extends Omit<PublicacaoListItem, 'resumo'> {
	id_djen: number;
	hash: string | null;
	link: string | null;
	link_certidao: string | null;
	motivo_cancelamento: string | null;
	unidade_id: number;
	capturada_em: string;
	atualizada_em: string | null;
	data_situacao: string | null;
	id_vinculado_por: number | null;
	destinatarios: DestinatarioPublicacao[];
	advogados: AdvogadoPublicacao[];
	/** HTML filtrado no backend (nh3, lista restrita de tags, sem atributos). */
	texto_html_seguro: string;
	pode_vincular: boolean;
}

export interface SincronizacaoDjen {
	id: number;
	inicio: string;
	fim: string | null;
	status: 'ok' | 'parcial' | 'erro';
	novas: number;
	atualizadas: number;
	vinculadas: number;
	mensagem: string | null;
}

/** `GET /api/djen/status`. */
export interface StatusDjen {
	ultima: SincronizacaoDjen | null;
	/** Mais de 2 dias úteis sem sincronizar (ou nunca sincronizou). */
	atrasada: boolean;
	/** Parâmetros da rotina neste servidor (DJEN_JANELA_DIAS, DJEN_MAX_PROCESSOS). */
	rotina: { janela_dias: number; max_processos: number };
	filtros: { tribunais: string[]; tipos: string[] };
}

/** `POST /api/processos/<id>/djen/buscar`. */
export interface BuscaProcessoDjen {
	novas: number;
	atualizadas: number;
	vinculadas: number;
	djen_consultado_em: string | null;
}

/** Linha de `GET /api/djen/oabs` (só admin). */
export interface OabMonitorada {
	id: number;
	numero_oab: string;
	uf_oab: string;
	/** `numero/UF`, como fica em `oab_origem` das publicações. */
	rotulo: string;
	ativo: boolean;
	unidade_id: number;
	unidade_nome: string | null;
	id_usuario: number | null;
	usuario_nome: string | null;
	criado_em: string;
	id_criado_por: number | null;
}

/** Corpo de `POST /api/djen/oabs` e `PUT /api/djen/oabs/<id>`. */
export interface OabMonitoradaInput {
	numero_oab?: string;
	uf_oab?: string;
	id_usuario?: number | null;
	unidade_id?: number;
	ativo?: boolean;
}

/** `GET /api/djen/oabs/sugestoes`: `usuarios.oab` reconhecível. */
export interface SugestaoOab {
	id_usuario: number;
	nome: string;
	urole: string;
	/** Texto livre do cadastro do usuário. */
	oab: string;
	numero_oab: string;
	uf_oab: string;
	cadastrada: boolean;
}

/** Item de `GET /api/djen/busca-parte`: consulta direta, nada gravado. */
export interface ItemBuscaParte {
	id_djen: number;
	data_disponibilizacao: string;
	numero_processo: string;
	numero_processo_mascara: string | null;
	sigla_tribunal: string | null;
	nome_orgao: string | null;
	tipo_comunicacao: string | null;
	tipo_documento: string | null;
	nome_classe: string | null;
	destinatarios: DestinatarioPublicacao[];
	resumo: string | null;
	link: string | null;
	ativo: boolean;
	/** A publicação já está gravada neste NPJ. */
	ja_no_banco: boolean;
	/** Id local, quando já gravada na unidade ativa. */
	publicacao_id: number | null;
	/** Processo da unidade com o mesmo número, se houver. */
	processo_id: number | null;
	processo_id_caso: number | null;
	/** Rótulo no banco de exemplos; nulo = ainda sem exemplo. */
	rotulo: RotuloExemplo | null;
}

export interface ResultadoBuscaParte {
	items: ItemBuscaParte[];
	total: number;
	/** O DJEN tinha mais resultados que o limite da busca. */
	truncado: boolean;
	nomes: string[];
	de: string;
	ate: string;
	tribunais: string[];
}

/** `POST /api/djen/busca-parte/importar`. */
export interface ImportacaoBuscaParte {
	novas: number;
	atualizadas: number;
	vinculadas: number;
	processos_criados: number[];
	nao_encontradas: number[];
}

/** Banco de exemplos rotulados (treino da sugestão automática). */
export type RotuloExemplo = 'relevante' | 'irrelevante' | 'nao_classificado';

export const ROTULO_EXEMPLO_LABEL: Record<RotuloExemplo, string> = {
	relevante: 'Relevante',
	irrelevante: 'Irrelevante',
	nao_classificado: 'Não analisado'
};

export type OrigemExemplo =
	| 'busca_parte'
	| 'vinculo_manual'
	| 'vinculo_automatico'
	| 'descarte'
	| 'classificacao'
	| 'captura';

export const ORIGEM_EXEMPLO_LABEL: Record<OrigemExemplo, string> = {
	busca_parte: 'Busca por parte',
	vinculo_manual: 'Vínculo manual',
	vinculo_automatico: 'Vínculo automático',
	descarte: 'Descarte',
	classificacao: 'Classificação manual',
	captura: 'Ainda não classificada'
};

/** `POST /api/djen/busca-parte/nao-pertinentes`. */
export interface NaoPertinentesBuscaParte {
	marcadas: number;
	/** Demais itens da consulta que entraram como "não revisada". */
	nao_revisadas: number;
	nao_encontradas: number[];
}

/** `GET /api/djen/exemplos/resumo` (só admin). */
export interface ResumoExemplos {
	total: number;
	por_rotulo: Record<RotuloExemplo, number>;
	por_origem: Partial<Record<OrigemExemplo, number>>;
	/** Exemplos que ainda guardam o texto (antes da retenção). */
	com_texto: number;
	/** Dias, contados do rótulo, até o texto dos rotulados ser apagado. */
	retencao_dias: number | null;
	/** Dias até as não revisadas serem apagadas. */
	retencao_nao_revisadas_dias: number | null;
}

/** Período máximo da busca por parte, em dias. */
export const BUSCA_PARTE_MAX_DIAS = 30;

export interface AcervoItem {
	partes?: string[];
	atendidos_sugeridos?: { id: number; nome: string }[];
	contextos?: ClassificacaoContexto[];
	id: number;
	id_djen: number;
	numero_processo: string;
	data_disponibilizacao: string;
	sigla_tribunal: string | null;
	nome_orgao: string | null;
	resumo: string | null;
	rotulo: RotuloExemplo;
	origem: string;
	situacao: string;
	comunicacao_id: number | null;
	id_processo: number | null;
	id_caso: number | null;
}
export interface ContextoDjen {
	treino_status?: 'ocioso' | 'na_fila' | 'executando' | 'concluido' | 'erro';
	treino_erro?: string | null;
	treino_solicitado_em?: string | null;
	treino_iniciado_em?: string | null;
	treino_finalizado_em?: string | null;
	id: number;
	nome: string;
	nomes: string[];
	tribunais: string[];
	contagens: Partial<Record<RotuloExemplo, number>>;
	pode_treinar: boolean;
	modelo: {
		id: number;
		metricas: { precisao: number; revocacao: number; f1: number; total: number };
	} | null;
}
export interface ClassificacaoContexto {
	contexto_id: number;
	nome: string;
	rotulo: RotuloExemplo;
	origem: string;
	sugestao: 'relevante' | 'irrelevante' | null;
	modelo_id: number | null;
}
export interface AcervoPagina {
	contextos?: ContextoDjen[];
	items: AcervoItem[];
	total: number;
	page: number;
	per_page: number;
}
export interface AcervoDetalhe extends Omit<Partial<Publicacao>, 'situacao'> {
	situacao?: string;
	comunicacao_id?: number | null;
	link?: string | null;
	link_certidao?: string | null;
	id: number;
	id_djen: number;
	texto_plano: string | null;
	rotulo: RotuloExemplo;
	historico: {
		contexto_nome?: string;
		rotulo_anterior: RotuloExemplo;
		rotulo: RotuloExemplo;
		origem: string;
		id_rotulado_por: number | null;
		rotulado_em: string;
	}[];
}

export type Monitoramento = {
	processo_id?: number | null;
	id: number;
	tipo: 'oab' | 'parte' | 'processo';
	valor: string;
	tribunais: string[];
	ativo: boolean;
	automatico: boolean;
	unidade_id: number;
	ultimo_sucesso: string | null;
};
export type LogMonitoramento = {
	duracao_segundos: number | null;
	id: number;
	origem: string;
	modo: string;
	inicio: string;
	fim: string | null;
	status: string;
	unidade_id: number;
	execucao_id: number | null;
	parametros: Record<string, string | number | null>;
	encontradas: number;
	novas: number;
	mensagem: string | null;
};
export type LogsMonitoramento = {
	agendamento?: { habilitado: boolean; janela_dias: number; janela_diurna_dias: number };
	items: LogMonitoramento[];
	total: number;
	page: number;
	per_page: number;
	retencao_dias: number;
};
