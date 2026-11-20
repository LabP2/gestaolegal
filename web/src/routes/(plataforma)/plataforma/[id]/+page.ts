import { plataforma } from '#lib/plataforma-client.ts';
import type { Tenant } from '#lib/types/index.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params, fetch }) => {
	const tenant = await plataforma.get<Tenant>(`tenants/${params.id}`, fetch);
	return { tenant };
};
