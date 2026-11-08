import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { api } from '$lib/api-client';
import { ApiException, type Publicacao } from '$lib/types';

export const load: PageLoad = async ({ params, fetch }) => {
	try {
		const publicacao = await api.get<Publicacao>(`djen/publicacoes/${params.id}`, {}, fetch);
		return { publicacao };
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 404, err.message);
		}
		throw err;
	}
};
