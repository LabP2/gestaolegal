import { api } from '#lib/api-client.ts';
import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import type { Monitoramento, LogsMonitoramento } from '#lib/types/djen.ts';
export const load: PageLoad = async ({ fetch, parent }) => {
	const { me } = await parent();
	if (!['admin', 'prof', 'orient'].includes(me.urole)) error(403, 'Acesso não permitido');
	const [monitoramentos, logs] = await Promise.all([
		api.get<Monitoramento[]>('djen/monitoramentos', {}, fetch),
		api.get<LogsMonitoramento>('djen/monitoramentos/logs', {}, fetch)
	]);
	return { monitoramentos, logs };
};
