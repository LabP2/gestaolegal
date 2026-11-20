import type { OrientacaoJuridica, Paginated } from '#lib/types/index.ts';
import { orientacaoSearchSchema } from '#lib/forms/schemas/orientacao-juridica-schema.ts';
import { zod4 } from 'sveltekit-superforms/adapters';
import { superValidate } from 'sveltekit-superforms/client';
import { api } from '#lib/api-client.ts';
import { error } from '@sveltejs/kit';
import { ApiException } from '#lib/types/index.ts';

export const load = async ({ depends, url, fetch }) => {
	depends('app:orientacoes-juridicas');

	const urlParams = url.searchParams;

	try {
		const data = await api.get<Paginated<OrientacaoJuridica>>(
			`orientacao_juridica?${urlParams.toString()}`,
			{},
			fetch
		);

		const formData = await superValidate(
			{
				search: urlParams.get('search') || '',
				show_inactive: urlParams.get('show_inactive') === 'true',
				area: urlParams.get('area') || 'todas'
			},
			zod4(orientacaoSearchSchema)
		);

		return {
			orientacoes: data,
			formData
		};
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 500, err.message);
		}
		throw err;
	}
};
