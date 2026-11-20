import { defineEnvVars } from '@sveltejs/kit/env';

// Opcional: em produção a API usa a mesma origem, via proxy do Nginx.
export const variables = defineEnvVars({
	PUBLIC_API_URL: { public: true, schema: (input) => input }
});
