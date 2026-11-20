import type { FilaHoje } from '#lib/types/index.ts';
import { api } from '#lib/api-client.ts';
import { error } from '@sveltejs/kit';
import { ApiException } from '#lib/types/index.ts';

export const load = async ({ fetch }) => {
	try {
		const fila = await api.get<FilaHoje>('fila_atendimento', {}, fetch);
		return { fila };
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 500, err.message);
		}
		throw err;
	}
};
