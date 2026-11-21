import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import pacote from './package.json' with { type: 'json' };

// Versão exibida em Sobre: uma fonte só, o package.json.
const version = pacote.version;

export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit({
			preprocess: vitePreprocess(),
			adapter: adapter({
				pages: 'build',
				assets: 'build',
				fallback: 'index.html' /* SPA fallback for client-side routing */,
				precompress: false,
				strict: true
			})
		})
	],
	define: { __VERSAO__: JSON.stringify(version) },
	envDir: '..'
});
