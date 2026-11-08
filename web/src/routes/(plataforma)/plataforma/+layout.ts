import { redirect } from '@sveltejs/kit';
import { plataforma, PLATAFORMA_LOGIN } from '$lib/plataforma-client';
import { ApiException, type PlataformaAdmin } from '$lib/types';
import type { LayoutLoad } from './$types';

// Sessão da plataforma, independente da do NPJ: só o cookie `plataforma_token`.
export const load: LayoutLoad = async ({ url, fetch }) => {
	if (url.pathname === PLATAFORMA_LOGIN) {
		return { admin: null };
	}
	try {
		const admin = await plataforma.get<PlataformaAdmin>('auth/me', fetch);
		return { admin };
	} catch (err) {
		if (err instanceof ApiException && err.statusCode === 401) {
			redirect(302, PLATAFORMA_LOGIN);
		}
		throw err;
	}
};
