import { error, redirect } from '@sveltejs/kit';
import type { Me } from '#lib/types/index.ts';
import type { LayoutLoad } from './$types';
import { api } from '#lib/api-client.ts';
import { ApiException } from '#lib/types/index.ts';
import { sincronizarUnidades } from '#lib/stores/unidade.ts';

export const load: LayoutLoad = async ({ url, fetch }) => {
	try {
		const me = await api.get<Me>('user/me', {}, fetch);
		// A unidade guardada só vale enquanto o vínculo existir: se o admin tirou
		// o usuário dela, cai para a primeira da lista.
		sincronizarUnidades(me.unidades);
		return { me };
	} catch (err) {
		if (err instanceof ApiException) {
			if (err.statusCode === 401) {
				const loginUrl = `/login?redirectTo=${encodeURIComponent(url.pathname + url.search)}`;
				redirect(302, loginUrl);
			}
			error(err.statusCode || 500, err.message);
		}
		error(500, 'Erro ao processar dados do usuário');
	}
};
