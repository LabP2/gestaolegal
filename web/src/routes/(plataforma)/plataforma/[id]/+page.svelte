<script lang="ts">
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import * as Card from '$lib/components/ui/card';
	import ConfirmAction from '$lib/components/confirm-action.svelte';
	import { plataforma } from '$lib/plataforma-client';
	import { ApiException, type Tenant } from '$lib/types';
	import { toast } from 'svelte-sonner';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let tenant = $state<Tenant | null>(null);
	let nome = $state('');
	let sigla = $state('');
	let instituicao = $state('');

	// A página é reaproveitada ao trocar de NPJ pela URL: o formulário segue o load.
	$effect(() => {
		tenant = data.tenant;
		nome = data.tenant.nome;
		sigla = data.tenant.sigla;
		instituicao = data.tenant.instituicao ?? '';
	});
	let erros = $state<Record<string, string>>({});
	let salvando = $state(false);

	async function salvar(event: SubmitEvent) {
		event.preventDefault();
		if (!tenant) return;
		erros = {};
		salvando = true;
		try {
			tenant = await plataforma.put<Tenant>(`tenants/${tenant.id}`, {
				nome,
				sigla,
				instituicao: instituicao.trim() || null
			});
			toast.success('Alterações salvas');
		} catch (err) {
			if (err instanceof ApiException && err.details?.field) {
				erros = { [err.details.field]: err.message };
			} else {
				toast.error(err instanceof ApiException ? err.message : 'Erro ao salvar.');
			}
		} finally {
			salvando = false;
		}
	}

	async function alternarAtivo() {
		if (!tenant) return;
		try {
			tenant = await plataforma.patch<Tenant>(`tenants/${tenant.id}/ativo`, {
				ativo: !tenant.ativo
			});
			toast.success(tenant.ativo ? 'NPJ ativado' : 'NPJ desativado');
		} catch (err) {
			toast.error(err instanceof ApiException ? err.message : 'Erro ao alterar a situação.');
		}
	}
</script>

{#if tenant}
	<div class="space-y-6">
		<div>
			<a href="/plataforma" class="text-sm text-muted-foreground hover:underline">← NPJs</a>
			<div class="flex flex-wrap items-center gap-3">
				<h1 class="text-2xl font-semibold">{tenant.sigla}</h1>
				<Badge variant={tenant.ativo ? 'default' : 'secondary'}>
					{tenant.ativo ? 'Ativo' : 'Desativado'}
				</Badge>
			</div>
			<p class="font-mono text-xs text-muted-foreground">{tenant.slug}</p>
		</div>

		<Card.Root>
			<Card.Header>
				<Card.Title class="text-base">Dados do NPJ</Card.Title>
				<Card.Description>O identificador não muda depois de criado.</Card.Description>
			</Card.Header>
			<Card.Content>
				<form class="grid gap-4 sm:grid-cols-2" onsubmit={salvar}>
					<div class="space-y-1">
						<Label for="nome">Nome</Label>
						<Input id="nome" bind:value={nome} required />
						{#if erros.nome}<p class="text-sm text-destructive">{erros.nome}</p>{/if}
					</div>
					<div class="space-y-1">
						<Label for="sigla">Sigla</Label>
						<Input id="sigla" bind:value={sigla} required />
						{#if erros.sigla}<p class="text-sm text-destructive">{erros.sigla}</p>{/if}
					</div>
					<div class="space-y-1 sm:col-span-2">
						<Label for="instituicao">Instituição (opcional)</Label>
						<Input id="instituicao" bind:value={instituicao} />
						{#if erros.instituicao}
							<p class="text-sm text-destructive">{erros.instituicao}</p>
						{/if}
					</div>
					<div class="sm:col-span-2">
						<Button type="submit" disabled={salvando}>{salvando ? 'Salvando…' : 'Salvar'}</Button>
					</div>
				</form>
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<Card.Title class="text-base">Situação</Card.Title>
				<Card.Description>
					{tenant.ativo
						? 'Desativar impede o login de todos os usuários deste NPJ e encerra as sessões abertas. Os dados ficam guardados.'
						: 'Este NPJ está desativado: ninguém dele consegue entrar.'}
				</Card.Description>
			</Card.Header>
			<Card.Content>
				<ConfirmAction
					title={tenant.ativo ? `Desativar ${tenant.sigla}?` : `Ativar ${tenant.sigla}?`}
					description={tenant.ativo
						? 'Os usuários deste NPJ deixam de entrar a partir de agora.'
						: 'Os usuários deste NPJ voltam a poder entrar.'}
					triggerText={tenant.ativo ? 'Desativar NPJ' : 'Ativar NPJ'}
					buttonVariant={tenant.ativo ? 'destructive' : 'default'}
					buttonSize="default"
					onConfirm={alternarAtivo}
				/>
			</Card.Content>
		</Card.Root>
	</div>
{/if}
