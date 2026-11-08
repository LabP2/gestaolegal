import { plataforma } from '$lib/plataforma-client';
import type { Tenant } from '$lib/types';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params, fetch }) => {
	const tenant = await plataforma.get<Tenant>(`tenants/${params.id}`, fetch);
	return { tenant };
};
