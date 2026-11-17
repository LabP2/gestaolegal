import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { api } from '$lib/api-client';
import type { AcervoPagina } from '$lib/types/djen';
import { ApiException, type Paginated, type PublicacaoListItem, type StatusDjen } from '$lib/types';

export const load: PageLoad = async ({ url, fetch, parent }) => {
	const { me } = await parent();
	try {
		const [publicacoes, status] = await Promise.all([
			api.get<Paginated<PublicacaoListItem>>(
				`djen/publicacoes?${url.searchParams.toString()}`,
				{},
				fetch
			),
			api.get<StatusDjen>('djen/status', {}, fetch)
		]);
		const acervo = ['admin', 'prof', 'orient'].includes(me.urole)
			? await api.get<AcervoPagina>(`djen/acervo?${url.searchParams}`, {}, fetch)
			: null;
		return { publicacoes, status, acervo };
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 500, err.message);
		}
		throw err;
	}
};
