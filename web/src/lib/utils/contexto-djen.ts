import type { CriteriosContexto } from '#lib/types/djen.ts';
import { formatDateOnly } from './date.ts';

const FONTES: Record<string, string> = {
	parte: 'Nome da parte',
	oab: 'OAB',
	processo: 'Número do processo'
};

/** Sugere um nome a partir dos critérios, sem acessar o formulário ou alterar seu estado. */
export function sugerirNomeContexto(filtros: CriteriosContexto): string {
	const nomes = [
		...new Set(
			[filtros.nome_parte ?? '', ...(filtros.nomes ?? [])]
				.map((nome) => nome.trim())
				.filter(Boolean)
		)
	];
	const partes = [
		nomes.length
			? `${nomes[0]}${nomes.length > 1 ? ` (+${nomes.length - 1} ${nomes.length === 2 ? 'variação' : 'variações'})` : ''}`
			: 'Publicações'
	];
	if (filtros.tribunal?.length) partes.push(filtros.tribunal.join(', '));
	if (filtros.polo) partes.push(filtros.polo === 'A' ? 'Polo ativo' : 'Polo passivo');
	if (filtros.numero_processo) partes.push(`Processo ${filtros.numero_processo}`);
	if (filtros.oab) partes.push(`OAB ${filtros.oab}`);
	if (filtros.fonte)
		partes.push(`Consulta por ${(FONTES[filtros.fonte] ?? filtros.fonte).toLowerCase()}`);
	if (filtros.inicio) partes.push(`De ${formatDateOnly(filtros.inicio)}`);
	if (filtros.fim) partes.push(`Até ${formatDateOnly(filtros.fim)}`);
	const nome = partes.length === 1 && !nomes.length ? 'Publicações da unidade' : partes.join(' · ');
	if (!filtros.inicio && !filtros.fim) {
		const sufixo = ' · Sem intervalo de tempo';
		return nome.slice(0, 150 - sufixo.length).trimEnd() + sufixo;
	}
	return nome.slice(0, 150);
}
