import { api } from '#lib/api-client.ts';
import { ApiException, type EstadoPresenca } from '#lib/types/index.ts';
import { error } from '@sveltejs/kit';

export const load = async ({ fetch }) => {
	try {
		const estado = await api.get<EstadoPresenca>('presenca/registro', {}, fetch);
		return { estado };
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 500, err.message);
		}
		throw err;
	}
};
