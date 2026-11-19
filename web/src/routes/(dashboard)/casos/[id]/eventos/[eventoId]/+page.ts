import type { PageLoad } from './$types';
import { api } from '#lib/api-client.ts';
import { error } from '@sveltejs/kit';
import { ApiException } from '#lib/types/index.ts';
import type { Evento } from '#lib/types/evento.ts';

export const load: PageLoad = async ({ params, fetch }) => {
	try {
		const evento = await api.get<Evento>(`caso/${params.id}/eventos/${params.eventoId}`, {}, fetch);

		return { evento };
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 500, err.message);
		}
		throw err;
	}
};
