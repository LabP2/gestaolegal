import { api } from '#lib/api-client.ts';
import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import type { ExecucoesMonitoramento } from '#lib/types/djen.ts';
export const load: PageLoad = async ({ fetch, parent }) => {
	const { me } = await parent();
	if (!['admin', 'prof', 'orient'].includes(me.urole)) error(403, 'Acesso não permitido');
	const execucoes = await api.get<ExecucoesMonitoramento>(
		'djen/monitoramentos/execucoes',
		{},
		fetch
	);
	return { execucoes };
};
