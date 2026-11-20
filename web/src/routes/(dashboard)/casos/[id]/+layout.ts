import { eventoCreateFormSchema } from '#lib/forms/schemas/evento-schema.ts';
import { processoCreateFormSchema } from '#lib/forms/schemas/processo-schema.ts';
import type { Caso } from '#lib/types/caso.ts';
import type { Evento } from '#lib/types/evento.ts';
import type { Paginated } from '#lib/types/paginated.ts';
import type { Historico, Lembrete } from '#lib/types/index.ts';
import { error } from '@sveltejs/kit';
import { superValidate } from 'sveltekit-superforms';
import { zod4 } from 'sveltekit-superforms/adapters';
import { api } from '#lib/api-client.ts';
import { ApiException } from '#lib/types/index.ts';

export const load = async ({ params, fetch }) => {
	try {
		const [caso, eventos, lembretes, historico] = await Promise.all([
			api.get<Caso>(`caso/${params.id}`, {}, fetch),
			api.get<Paginated<Evento>>(`caso/${params.id}/eventos`, {}, fetch),
			api.get<Lembrete[]>(`caso/${params.id}/lembretes`, {}, fetch),
			api.get<Paginated<Historico>>(`caso/${params.id}/historico`, {}, fetch)
		]);

		const eventoFormData = await superValidate(zod4(eventoCreateFormSchema));
		const processoFormData = await superValidate(zod4(processoCreateFormSchema));

		return {
			caso,
			eventos,
			lembretes,
			historico,
			eventoFormData,
			processoFormData
		};
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 404, err.message);
		}
		throw err;
	}
};
