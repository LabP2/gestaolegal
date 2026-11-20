import type { Roteiro } from '#lib/types/index.ts';
import { api } from '#lib/api-client.ts';
import { error } from '@sveltejs/kit';
import { ApiException } from '#lib/types/index.ts';

export const load = async ({ fetch, depends }) => {
	depends('app:roteiros');
	try {
		const roteiros = await api.get<Roteiro[]>('roteiro', {}, fetch);
		return { roteiros };
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 500, err.message);
		}
		throw err;
	}
};
