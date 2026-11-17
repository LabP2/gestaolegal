import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => {
	const params = new URLSearchParams(url.searchParams);
	params.set('situacao', 'pendente');
	redirect(307, `/djen?${params}`);
};
