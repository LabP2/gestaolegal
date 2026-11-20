import { error, redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { api } from '#lib/api-client.ts';
import { ApiException } from '#lib/types/index.ts';
import type { AcervoPagina } from '#lib/types/djen.ts';
export const load: PageLoad = async ({ url, fetch }) => {
	if (url.searchParams.get('contexto_id') && !url.searchParams.has('rotulo')) {
		const params = new URLSearchParams(url.searchParams);
		params.set('rotulo', 'nao_classificado');
		redirect(307, `${url.pathname}?${params}`);
	}
	try {
		const params = new URLSearchParams(url.searchParams);
		params.set('texto_integral', '1');
		return { acervo: await api.get<AcervoPagina>(`djen/acervo?${params}`, {}, fetch) };
	} catch (err) {
		if (err instanceof ApiException) error(err.statusCode || 500, err.message);
		throw err;
	}
};
