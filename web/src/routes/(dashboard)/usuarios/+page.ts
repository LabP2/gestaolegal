import { error } from '@sveltejs/kit';
import type { Paginated, User } from '#lib/types/index.ts';
import { api } from '#lib/api-client.ts';
import { ApiException } from '#lib/types/index.ts';

export const load = async ({ url, fetch }) => {
	const urlParams = url.searchParams;

	try {
		const data = await api.get<Paginated<User>>(`user?${urlParams.toString()}`, {}, fetch);

		return {
			users: data,
			canManageUsers: true
		};
	} catch (err) {
		if (err instanceof ApiException) {
			error(err.statusCode || 500, err.message);
		}
		throw err;
	}
};
