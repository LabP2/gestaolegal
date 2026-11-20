import { superValidate } from 'sveltekit-superforms';
import { zod4 } from 'sveltekit-superforms/adapters';
import { processoCreateFormSchema } from '#lib/forms/schemas/processo-schema.ts';
import { error, redirect } from '@sveltejs/kit';
import { api } from '#lib/api-client.ts';
import { toISODateInput } from '#lib/utils/date.ts';
import { ApiException, type ProcessoDetalhe } from '#lib/types/index.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params, fetch }) => {
	let processo: ProcessoDetalhe;
	try {
		processo = await api.get<ProcessoDetalhe>(`processos/${params.id}`, {}, fetch);
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 500, err.message);
		}
		throw err;
	}
	// Processo de caso se edita pela tela do caso.
	if (processo.id_caso !== null) {
		redirect(307, `/casos/${processo.id_caso}/processos/${processo.id}/editar`);
	}
	const form = await superValidate(
		{
			...processo,
			data_distribuicao: toISODateInput(processo.data_distribuicao) ?? null,
			data_transito_em_julgado: toISODateInput(processo.data_transito_em_julgado) ?? null
		},
		zod4(processoCreateFormSchema),
		{ id: `processo-sem-caso-editar-${params.id}` }
	);
	return { form, processo };
};
