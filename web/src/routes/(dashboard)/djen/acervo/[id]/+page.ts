import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { api } from '#lib/api-client.ts';
import { ApiException } from '#lib/types/index.ts';
import type { AcervoDetalhe } from '#lib/types/djen.ts';

export const load: PageLoad = async ({ params, fetch, url }) => {
	try {
		const publicacao = await api.get<AcervoDetalhe>(`djen/acervo/${params.id}`, {}, fetch);
		const destino = url.searchParams.get('voltar') || '/djen';
		// Only local list routes: query parameters must never become an open redirect.
		const voltar = /^\/djen(?:\/classificacao)?(?:\?[^#]*)?$/.test(destino) ? destino : '/djen';
		return { publicacao, voltar };
	} catch (err) {
		if (err instanceof ApiException) error(err.statusCode || 404, err.message);
		throw err;
	}
};
