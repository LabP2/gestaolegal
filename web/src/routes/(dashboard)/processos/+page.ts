import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { api } from '$lib/api-client';
import { ApiException, type PaginaProcessos } from '$lib/types';

export const load: PageLoad = async ({ url, fetch }) => {
	try {
		const processos = await api.get<PaginaProcessos>(
			`processos?${url.searchParams.toString()}`,
			{},
			fetch
		);
		return { processos };
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 500, err.message);
		}
		throw err;
	}
};
