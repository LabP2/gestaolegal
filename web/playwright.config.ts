import { defineConfig } from '@playwright/test';

export default defineConfig({
	testDir: '../tests/browser',
	testMatch: 'frontend.spec.cjs',
	workers: 1,
	timeout: 45_000,
	use: {
		baseURL: 'http://127.0.0.1:5302',
		launchOptions: {
			executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome',
			args: ['--no-sandbox']
		}
	},
	webServer: {
		command: 'npm run dev -- --host 127.0.0.1 --port 5302 --strictPort',
		url: 'http://127.0.0.1:5302/login',
		env: { PUBLIC_API_URL: 'http://127.0.0.1:5302' },
		timeout: 120_000,
		reuseExistingServer: false
	}
});
