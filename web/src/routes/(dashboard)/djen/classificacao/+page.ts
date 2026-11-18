import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { api } from '$lib/api-client';
import { ApiException } from '$lib/types';
import type { AcervoPagina, ContextoDjen } from '$lib/types/djen';
export const load: PageLoad = async ({ url, fetch }) => {
	const p = new URLSearchParams();
	for (const campo of ['contexto_id', 'rotulo', 'numero_processo', 'inicio', 'fim', 'page']) {
		if (url.searchParams.has(campo)) p.set(campo, url.searchParams.get(campo)!);
	}
	if (p.has('contexto_id') && !p.has('rotulo')) p.set('rotulo', 'nao_classificado');
	try {
		if (!p.get('contexto_id')) {
			const contextos = await api.get<ContextoDjen[]>('djen/contextos', {}, fetch);
			return { acervo: { items: [], total: 0, page: 1, per_page: 20, contextos } as AcervoPagina };
		}
		return { acervo: await api.get<AcervoPagina>(`djen/acervo?${p}`, {}, fetch) };
	} catch (err) {
		if (err instanceof ApiException) error(err.statusCode || 500, err.message);
		throw err;
	}
};
