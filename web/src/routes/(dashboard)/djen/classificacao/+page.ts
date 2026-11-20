import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { api } from '#lib/api-client.ts';
import { ApiException } from '#lib/types/index.ts';
import type { AcervoPagina } from '#lib/types/djen.ts';
export const load: PageLoad = async ({ url, fetch }) => {
	try {
		return { acervo: await api.get<AcervoPagina>(`djen/acervo?${url.searchParams}`, {}, fetch) };
	} catch (err) {
		if (err instanceof ApiException) error(err.statusCode || 500, err.message);
		throw err;
	}
};
