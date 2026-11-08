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
	filtros: { tribunais: string[]; tipos: string[] };
}

/** `POST /api/processos/<id>/djen/buscar`. */
export interface BuscaProcessoDjen {
	novas: number;
	atualizadas: number;
	vinculadas: number;
	djen_consultado_em: string | null;
}
