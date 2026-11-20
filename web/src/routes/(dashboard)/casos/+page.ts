import type { ListCaso, Paginated } from '#lib/types/index.ts';
import { api } from '#lib/api-client.ts';
import { error } from '@sveltejs/kit';
import { ApiException } from '#lib/types/index.ts';

export const load = async ({ url, fetch }) => {
	const urlParams = new URLSearchParams(url.searchParams);
	if (!urlParams.has('per_page')) urlParams.set('per_page', '20');

	try {
		const data = await api.get<Paginated<ListCaso>>(`caso?${urlParams.toString()}`, {}, fetch);
		return { data };
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 500, err.message);
		}
		throw err;
	}
};
