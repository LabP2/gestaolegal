import { ARQUIVO_PAPEIS_EDITAM } from '#lib/types/index.ts';
import { error } from '@sveltejs/kit';

export const load = async ({ parent }) => {
	const { me } = await parent();
	if (!ARQUIVO_PAPEIS_EDITAM.includes(me.urole)) {
		error(403, 'Você não tem permissão para cadastrar arquivos. Contate o administrador.');
	}
	return {};
};
