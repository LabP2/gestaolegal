import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { api } from '$lib/api-client';
import { ApiException } from '$lib/types';
import type { AcervoPagina } from '$lib/types/djen';
export const load: PageLoad = async ({ url, fetch }) => {
	const p = new URLSearchParams(url.searchParams);
	if (!p.has('rotulo')) p.set('rotulo', 'nao_classificado');
	try {
		return { acervo: await api.get<AcervoPagina>(`djen/acervo?${p}`, {}, fetch) };
	} catch (err) {
		if (err instanceof ApiException) error(err.statusCode || 500, err.message);
		throw err;
	}
};
