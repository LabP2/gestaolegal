import type { ListAssistenciaJudiciaria, Paginated } from '#lib/types/index.ts';
import { assistenciaJudiciariaSearchSchema } from '#lib/forms/schemas/assistencia-judiciaria-schema.ts';
import { zod4 } from 'sveltekit-superforms/adapters';
import { superValidate } from 'sveltekit-superforms/client';
import { api } from '#lib/api-client.ts';
import { error } from '@sveltejs/kit';
import { ApiException } from '#lib/types/index.ts';

export const load = async ({ depends, url, fetch }) => {
	depends('app:assistencias-judiciarias');

	const urlParams = url.searchParams;

	try {
		const data = await api.get<Paginated<ListAssistenciaJudiciaria>>(
			`assistencia_judiciaria?${urlParams.toString()}`,
			{},
			fetch
		);

		const formData = await superValidate(
			{
				search: urlParams.get('search') || '',
				show_inactive: urlParams.get('show_inactive') === 'true',
				area: urlParams.get('area') || 'todas',
				regiao: urlParams.get('regiao') || 'todas'
			},
			zod4(assistenciaJudiciariaSearchSchema)
		);

		return {
			assistencias: data,
			formData
		};
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 500, err.message);
		}
		throw err;
	}
};
