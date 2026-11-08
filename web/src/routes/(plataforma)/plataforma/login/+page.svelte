<script lang="ts">
	import { goto } from '$app/navigation';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import * as Card from '$lib/components/ui/card';
	import { guardarTokenPlataforma, plataforma } from '$lib/plataforma-client';
	import { ApiException, type PlataformaAdmin } from '$lib/types';

	let email = $state('');
	let password = $state('');
	let erro = $state<string | null>(null);
	let enviando = $state(false);

	async function entrar(event: SubmitEvent) {
		event.preventDefault();
		erro = null;
		enviando = true;
		try {
			const dados = await plataforma.post<{ token: string; admin: PlataformaAdmin }>('auth/login', {
				email,
				password
			});
			guardarTokenPlataforma(dados.token);
			goto('/plataforma');
		} catch (err) {
			erro =
				err instanceof ApiException && err.statusCode === 401
					? 'E-mail ou senha incorretos.'
					: err instanceof ApiException
						? err.message
						: 'Não foi possível conectar ao servidor.';
		} finally {
			enviando = false;
		}
	}
</script>

<div class="flex min-h-[70vh] items-center justify-center">
	<Card.Root class="w-full max-w-sm">
		<Card.Header>
			<Card.Title>Administração da plataforma</Card.Title>
			<Card.Description>
				Acesso restrito a quem cadastra os NPJs. Contas de NPJ entram em
				<a href="/login" class="underline">/login</a>.
			</Card.Description>
		</Card.Header>
		<Card.Content>
			<form class="space-y-4" onsubmit={entrar}>
				<div class="space-y-2">
					<Label for="email">E-mail</Label>
					<Input id="email" type="email" autocomplete="username" bind:value={email} required />
				</div>
				<div class="space-y-2">
					<Label for="password">Senha</Label>
					<Input
						id="password"
						type="password"
						autocomplete="current-password"
						bind:value={password}
						required
					/>
				</div>
				{#if erro}
					<p role="alert" class="text-sm text-destructive">{erro}</p>
				{/if}
				<Button type="submit" class="w-full" disabled={enviando}>
					{enviando ? 'Entrando…' : 'Entrar'}
				</Button>
			</form>
		</Card.Content>
	</Card.Root>
</div>
