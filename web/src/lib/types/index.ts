// API response types
export type { ApiResponse, ApiError } from './api-response';
export { ApiException } from './api-response';

// Domain types
export type { Me, TenantIdentificacao, User, UserOption } from './user';
export type { OrientacaoJuridica } from './orientacao-juridica';
export type {
	AssistenciaJudiciaria,
	ListAssistenciaJudiciaria,
	OrientacaoResumo
} from './assistencia-judiciaria';
export type { Lembrete } from './lembrete';
export type { Historico } from './historico';
export type { Roteiro } from './roteiro';
export type { Arquivo, ListArquivo } from './arquivo';
export type { Notificacao, FiltroArquivadas } from './notificacao';
export { destinoDaNotificacao, FILTROS_ARQUIVADAS } from './notificacao';
export { ARQUIVO_PAPEIS_EDITAM, ARQUIVO_PAPEIS_EXCLUEM } from './arquivo';
export type { Atendido, ListAtendido, AtendidoNome, AtendidoSimplificadoInput } from './atendido';
export type { Paginated, PaginationMeta } from './paginated';
export type { Endereco } from './endereco';
export type { Unidade } from './unidade';
export type { Caso, ListCaso } from './caso';
export type {
	Processo,
	ListProcesso,
	ProcessoCreateInput,
	ProcessoUpdateInput,
	PoloParte,
	ParteProcesso,
	ProcessoDetalhe,
	ProcessoListItem,
	PaginaProcessos,
	ProcessoSemCasoInput
} from './processo';
export { POLO_PARTE_LABEL, PROCESSO_PAPEIS_SEM_CASO } from './processo';
export type { SearchResultGroup, SearchResults, SearchResponse, SearchResultItem } from './search';
export type { FilaItem, FilaHoje, SenhaPreview } from './fila-atendimento';
export { FilaPrioridade, FilaStatus } from './fila-atendimento';
export type {
	JanelaPlantao,
	DiaAberto,
	EscalaItem,
	MinhaMarcacao,
	PaginaPlantao,
	ConfiguracaoPlantao,
	StatusPresenca,
	EstadoPresenca,
	RegistroPresencaResultado,
	PresencaPendente,
	PlantaoPendente,
	Pendencias,
	ConfirmacaoItem,
	Confirmacao
} from './plantao';
export { CONFIRMACAO } from './plantao';
export type { ResumoEscala } from './plantao';
export type {
	Tenant,
	PlataformaAdmin,
	TenantCriacaoInput,
	TenantEdicaoInput,
	TenantCriado
} from './tenant';
export type {
	SituacaoPublicacao,
	PublicacaoListItem,
	Publicacao,
	DestinatarioPublicacao,
	AdvogadoPublicacao,
	SincronizacaoDjen,
	StatusDjen,
	BuscaProcessoDjen,
	OabMonitorada,
	OabMonitoradaInput,
	SugestaoOab,
	ItemBuscaParte,
	ResultadoBuscaParte,
	ImportacaoBuscaParte,
	RotuloExemplo,
	OrigemExemplo,
	NaoPertinentesBuscaParte,
	ResumoExemplos
} from './djen';
export {
	SITUACAO_PUBLICACAO_LABEL,
	DJEN_PAPEIS_GESTAO,
	BUSCA_PARTE_MAX_DIAS,
	ROTULO_EXEMPLO_LABEL,
	ORIGEM_EXEMPLO_LABEL
} from './djen';
