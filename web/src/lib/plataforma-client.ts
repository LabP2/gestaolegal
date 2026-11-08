/**
 * Cliente da API da plataforma (`/api/plataforma`).
 *
 * Separado do `api-client.ts` de propósito: usa o cookie `plataforma_token`,
 * nunca o `auth_token` do NPJ, e não envia `X-Unidade-Id`. As duas sessões não
 * se misturam (docs/plano-multitenant.md §6.4).
 */
import { getApiBaseUrl, unwrapApiResponse } from './api-client';

export const PLATAFORMA_COOKIE = 'plataforma_token';
export const PLATAFORMA_LOGIN = '/plataforma/login';

export function tokenPlataforma(): string | null {
	if (typeof document === 'undefined') return null;
	const cookie = document.cookie.split('; ').find((row) => row.startsWith(`${PLATAFORMA_COOKIE}=`));
	return cookie ? cookie.split('=')[1] : null;
}

export function guardarTokenPlataforma(token: string): void {
	// Mesma duração do token emitido pela API (8 h).
	const maxAge = 60 * 60 * 8;
	const secure = window.location.protocol === 'https:' ? '; Secure' : '';
	document.cookie = `${PLATAFORMA_COOKIE}=${token}; Path=/; Max-Age=${maxAge}; SameSite=Strict${secure}`;
}

export function sairDaPlataforma(): void {
	document.cookie = `${PLATAFORMA_COOKIE}=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;`;
}

async function chamar<T>(
	endpoint: string,
	init: RequestInit = {},
	customFetch: typeof fetch = fetch
): Promise<T> {
	const headers = new Headers(init.headers || {});
	const token = tokenPlataforma();
	if (token) headers.set('Authorization', `Bearer ${token}`);
	if (typeof init.body === 'string') headers.set('Content-Type', 'application/json');

	const limpo = endpoint.startsWith('/') ? endpoint.slice(1) : endpoint;
	const response = await customFetch(`${getApiBaseUrl()}/plataforma/${limpo}`, {
		...init,
		headers,
		credentials: 'include'
	});

	if (response.status === 401 && typeof window !== 'undefined') {
		sairDaPlataforma();
		if (window.location.pathname !== PLATAFORMA_LOGIN) {
			window.location.href = PLATAFORMA_LOGIN;
		}
	}

	return unwrapApiResponse<T>(response);
}

const corpo = (data: unknown) => (data === undefined ? undefined : JSON.stringify(data));

export const plataforma = {
	get: <T>(endpoint: string, customFetch?: typeof fetch) =>
		chamar<T>(endpoint, { method: 'GET' }, customFetch),
	post: <T>(endpoint: string, data?: unknown) =>
		chamar<T>(endpoint, { method: 'POST', body: corpo(data) }),
	put: <T>(endpoint: string, data?: unknown) =>
		chamar<T>(endpoint, { method: 'PUT', body: corpo(data) }),
	patch: <T>(endpoint: string, data?: unknown) =>
		chamar<T>(endpoint, { method: 'PATCH', body: corpo(data) })
};
