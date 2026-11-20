import { superValidate } from 'sveltekit-superforms';
import { zod4 } from 'sveltekit-superforms/adapters';
import { processoCreateFormSchema } from '#lib/forms/schemas/processo-schema.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async () => {
	const form = await superValidate(zod4(processoCreateFormSchema), { id: 'processo-sem-caso' });
	return { form };
};
