import { api } from '#lib/api-client.ts';
import type { ResumoEscala } from '#lib/types/index.ts';

export const load = async ({ fetch }) => ({
	escalas: await api.get<ResumoEscala[]>('plantao/escalas', {}, fetch)
});
