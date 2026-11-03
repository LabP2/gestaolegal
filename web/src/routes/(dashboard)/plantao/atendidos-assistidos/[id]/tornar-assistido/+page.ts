import { superValidate } from 'sveltekit-superforms';
import { error } from '@sveltejs/kit';
import { zod4 } from 'sveltekit-superforms/adapters';
import { assistidoCreateFormSchema } from '$lib/forms/schemas/assistido-schema';
import type { PageLoad } from './$types';
import { api } from '$lib/api-client';
import { ApiException } from '$lib/types';
import type { Atendido } from '$lib/types';

export const load: PageLoad = async ({ params, fetch }) => {
	try {
		const atendido = await api.get<Atendido>(`atendido/${params.id}`, {}, fetch);

		if (atendido.assistido) {
			error(400, 'Este atendido já é um assistido');
		}

		const form = await superValidate(
			atendido.pj_constituida === 'sim'
				? { assistido_pessoa_juridica: { enquadramento: '' as const, socios: [''] } }
				: {},
			zod4(assistidoCreateFormSchema),
			{ errors: false }
		);

		return { form, atendido };
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 404, err.message);
		}
		throw err;
	}
};
