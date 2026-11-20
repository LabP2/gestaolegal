import { passwordChangeSchema } from '#lib/forms/schemas/password-schema.ts';
import { superValidate } from 'sveltekit-superforms';
import { zod4 } from 'sveltekit-superforms/adapters';
import type { PageLoad } from './$types';
import { api } from '#lib/api-client.ts';
import { error } from '@sveltejs/kit';
import { ApiException } from '#lib/types/index.ts';
import type { User } from '#lib/types/index.ts';

export const load: PageLoad = async ({ params, fetch }) => {
	const userId = params.id;

	try {
		const user = await api.get<User>(`user/${userId}`, {}, fetch);
		const form = await superValidate(zod4(passwordChangeSchema));

		return {
			user,
			form
		};
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 404, err.message);
		}
		throw err;
	}
};
