import { superValidate } from 'sveltekit-superforms';
import { error } from '@sveltejs/kit';
import { zod4 } from 'sveltekit-superforms/adapters';
import { atendidoUpdateFormSchema, legacyEditSchema } from '$lib/forms/schemas/atendido-schema';
import { assistidoUpdateFormSchema } from '$lib/forms/schemas/assistido-schema';
import type { PageLoad } from './$types';
import { api } from '$lib/api-client';
import { ApiException } from '$lib/types';
import type { Atendido } from '$lib/types';
import { toISODateInput } from '$lib/utils/date';

export const load: PageLoad = async ({ params, fetch }) => {
	try {
		const atendido = await api.get<Atendido>(`atendido/${params.id}`, {}, fetch);

		// The API returns the address as a nested `endereco` object, but the form
		// schema expects flat address fields. Flatten it so the edit form is
		// pre-populated (and don't let endereco.id clobber the atendido id).
		const { endereco, ...atendidoRest } = atendido;
		// Dados da API ainda não validados: o schema abaixo verifica enums e campos legados.
		const atendidoFormSource: Record<string, unknown> = {
			...atendidoRest,
			// The API serializes dates as GMT strings; the form's date picker needs
			// ISO "YYYY-MM-DD" or the update request fails backend validation.
			data_nascimento: toISODateInput(atendidoRest.data_nascimento),
			nascimento_repres_legal: toISODateInput(
				(atendidoRest as { nascimento_repres_legal?: string }).nascimento_repres_legal
			),
			logradouro: endereco?.logradouro,
			numero: endereco?.numero,
			complemento: endereco?.complemento,
			bairro: endereco?.bairro,
			cep: endereco?.cep,
			cidade: endereco?.cidade,
			estado: endereco?.estado
		};

		// Não transformar ausência de resposta em “não”.
		for (const field of ['cpf', 'procurou_outro_local', 'pj_constituida']) {
			atendidoFormSource[field] ??= '';
		}
		const atendidoForm = await superValidate(
			atendidoFormSource,
			zod4(atendido.sem_triagem ? atendidoUpdateFormSchema : legacyEditSchema(atendidoFormSource))
		);

		let assistidoForm = null;
		if (atendido.assistido) {
			assistidoForm = await superValidate(
				{
					...atendido.assistido,
					assistido_pessoa_juridica:
						atendido.pj_constituida === 'sim'
							? (atendido.assistido.assistido_pessoa_juridica ?? {
									enquadramento: '' as const,
									socios: ['']
								})
							: null
				},
				zod4(assistidoUpdateFormSchema),
				{ errors: false }
			);
		}

		return {
			form: atendidoForm,
			legacyOriginal: atendido.sem_triagem ? undefined : atendidoFormSource,
			atendidoForm,
			assistidoForm,
			atendido,
			isAssistido: !!atendido.assistido
		};
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 404, err.message);
		}
		throw err;
	}
};
