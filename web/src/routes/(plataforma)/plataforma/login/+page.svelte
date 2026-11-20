<script lang="ts">
	import Eye from '@lucide/svelte/icons/eye';
	import EyeOff from '@lucide/svelte/icons/eye-off';
	import { goto } from '$app/navigation';
	import { Button } from '#lib/components/ui/button/index.ts';
	import { Input } from '#lib/components/ui/input/index.ts';
	import { Label } from '#lib/components/ui/label/index.ts';
	import * as Card from '#lib/components/ui/card/index.ts';
	import { guardarTokenPlataforma, plataforma } from '#lib/plataforma-client.ts';
	import { ApiException, type PlataformaAdmin } from '#lib/types/index.ts';

	let email = $state('');
	let password = $state('');
	let mostrarSenha = $state(false);
	let erro = $state<string | null>(null);
	let enviando = $state(false);

	async function entrar(event: SubmitEvent) {
		event.preventDefault();
		erro = null;
		enviando = true;
		try {
			const dados = await plataforma.post<{ token: string; admin: PlataformaAdmin }>('auth/login', {
				email: email.trim(),
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
					<div class="relative">
						<Input
							id="password"
							type={mostrarSenha ? 'text' : 'password'}
							autocomplete="current-password"
							bind:value={password}
							required
							class="pr-12"
						/>
						<button
							type="button"
							class="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-md text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
							aria-label={mostrarSenha ? 'Ocultar senha' : 'Mostrar senha'}
							aria-controls="password"
							aria-pressed={mostrarSenha}
							onclick={() => (mostrarSenha = !mostrarSenha)}
						>
							{#if mostrarSenha}<EyeOff class="h-4 w-4" aria-hidden="true" />{:else}<Eye
									class="h-4 w-4"
									aria-hidden="true"
								/>{/if}
						</button>
					</div>
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
