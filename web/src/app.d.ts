// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	/** Versão do sistema, lida do package.json no build (vite.config.ts). */
	const __VERSAO__: string;
	namespace App {
		interface Error {
			message: string;
		}
		interface Locals {
			auth_token: string | null | undefined;
		}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}
}

export {};
