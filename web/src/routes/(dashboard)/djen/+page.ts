import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { api } from '$lib/api-client';
import { ApiException, type Paginated, type PublicacaoListItem, type StatusDjen } from '$lib/types';

export const load: PageLoad = async ({ url, fetch }) => {
	try {
		const [publicacoes, status] = await Promise.all([
			api.get<Paginated<PublicacaoListItem>>(
				`djen/publicacoes?${url.searchParams.toString()}`,
				{},
				fetch
			),
			api.get<StatusDjen>('djen/status', {}, fetch)
		]);
		return { publicacoes, status };
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 500, err.message);
		}
		throw err;
	}
};
