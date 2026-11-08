import { page } from '$app/state';

/**
 * Sigla do NPJ da conta, para textos que antes diziam "DAJ" fixo.
 *
 * Lê o `me` carregado pelo layout do dashboard; fora dele (ou antes do
 * carregamento) cai no genérico "NPJ".
 */
export function siglaNpj(): string {
	return page.data?.me?.tenant?.sigla ?? 'NPJ';
}
