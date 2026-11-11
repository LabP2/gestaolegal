/** Publicações do DJEN (docs/plano-djen.md, §5). Contrato: revisão humana. */

export type SituacaoPublicacao = 'vinculada' | 'pendente' | 'descartada';

export const SITUACAO_PUBLICACAO_LABEL: Record<SituacaoPublicacao, string> = {
	vinculada: 'Vinculada',
	pendente: 'Sem caso',
	descartada: 'Descartada'
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
export type RotuloExemplo = 'pertinente' | 'nao_pertinente' | 'nao_revisada';

export const ROTULO_EXEMPLO_LABEL: Record<RotuloExemplo, string> = {
	pertinente: 'Pertinente',
	nao_pertinente: 'Não pertinente',
	nao_revisada: 'Não revisada'
};

export type OrigemExemplo = 'busca_parte' | 'vinculo_manual' | 'vinculo_automatico' | 'descarte';

export const ORIGEM_EXEMPLO_LABEL: Record<OrigemExemplo, string> = {
	busca_parte: 'Busca por parte',
	vinculo_manual: 'Vínculo manual',
	vinculo_automatico: 'Vínculo automático',
	descarte: 'Descarte'
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
	retencao_dias: number;
	/** Dias até as não revisadas serem apagadas. */
	retencao_nao_revisadas_dias: number;
}

/** Período máximo da busca por parte, em dias. */
export const BUSCA_PARTE_MAX_DIAS = 30;
