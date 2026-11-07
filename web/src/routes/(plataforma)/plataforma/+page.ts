import { plataforma } from '$lib/plataforma-client';
import type { Tenant } from '$lib/types';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ url, fetch }) => {
	const q = url.searchParams.get('q') ?? '';
	const ativo = url.searchParams.get('ativo') ?? '';
	const params = new URLSearchParams();
	if (q) params.set('q', q);
	if (ativo) params.set('ativo', ativo);
	const sufixo = params.size ? `?${params}` : '';
	const { items } = await plataforma.get<{ items: Tenant[] }>(`tenants${sufixo}`, fetch);
	return { tenants: items, q, ativo };
};
