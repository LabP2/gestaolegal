import { error } from '@sveltejs/kit';
import { api } from '$lib/api-client';
import { ApiException, type OabMonitorada, type SugestaoOab } from '$lib/types';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ parent, fetch }) => {
	const { me } = await parent();
	if (me.urole !== 'admin') {
		error(403, 'Só o administrador mantém a lista de OABs monitoradas.');
	}
	try {
		const [oabs, sugestoes] = await Promise.all([
			api.get<OabMonitorada[]>('djen/oabs', {}, fetch),
			api.get<SugestaoOab[]>('djen/oabs/sugestoes', {}, fetch)
		]);
		return { oabs, sugestoes };
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 500, err.message);
		}
		throw err;
	}
};
