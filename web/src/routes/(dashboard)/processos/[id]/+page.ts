import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { api } from '#lib/api-client.ts';
import { ApiException, type ProcessoDetalhe } from '#lib/types/index.ts';

export const load: PageLoad = async ({ params, fetch }) => {
	try {
		const processo = await api.get<ProcessoDetalhe>(`processos/${params.id}`, {}, fetch);
		return { processo };
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 404, err.message);
		}
		throw err;
	}
};
