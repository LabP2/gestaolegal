import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { api } from '#lib/api-client.ts';
import type { AcervoPagina } from '#lib/types/djen.ts';
import {
	ApiException,
	type Paginated,
	type PublicacaoListItem,
	type StatusDjen
} from '#lib/types/index.ts';

export const load: PageLoad = async ({ url, fetch, parent }) => {
	const { me } = await parent();
	try {
		// Gestão vê só o acervo. Os filtros dele (ex.: situacao=nao_importada) não
		// existem em djen/publicacoes, que responderia 400 e derrubaria a página.
		if (['admin', 'prof', 'orient'].includes(me.urole)) {
			const acervo = await api.get<AcervoPagina>(`djen/acervo?${url.searchParams}`, {}, fetch);
			return { acervo, publicacoes: null, status: null };
		}
		const [publicacoes, status] = await Promise.all([
			api.get<Paginated<PublicacaoListItem>>(
				`djen/publicacoes?${url.searchParams.toString()}`,
				{},
				fetch
			),
			api.get<StatusDjen>('djen/status', {}, fetch)
		]);
		return { acervo: null, publicacoes, status };
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 500, err.message);
		}
		throw err;
	}
};
