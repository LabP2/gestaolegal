import { api } from '#lib/api-client.ts';
import type { Ambiente } from '#lib/types/index.ts';

let consulta: Promise<boolean> | null = null;

/**
 * Diz se a API roda em modo de demonstração (`DEMO_MODE`). A resposta não
 * muda durante a sessão, então a consulta é feita uma vez só. Falha de rede ou
 * API antiga sem a rota contam como "não é demo": o aviso é só informativo e
 * não pode travar o login.
 */
export function ambienteDemo(): Promise<boolean> {
	consulta ??= api
		.get<Ambiente>('ambiente')
		.then((ambiente) => ambiente?.demo === true)
		.catch(() => false);
	return consulta;
}
