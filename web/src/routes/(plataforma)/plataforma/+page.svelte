<script lang="ts">
	import { goto } from '$app/navigation';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import * as Table from '$lib/components/ui/table';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let q = $state('');
	let ativo = $state('');

	// Os filtros acompanham a URL (voltar/avançar do navegador).
	$effect(() => {
		q = data.q;
		ativo = data.ativo;
	});

	function filtrar(event: SubmitEvent) {
		event.preventDefault();
		const params = new URLSearchParams();
		if (q.trim()) params.set('q', q.trim());
		if (ativo) params.set('ativo', ativo);
		goto(`/plataforma${params.size ? `?${params}` : ''}`, { keepFocus: true });
	}
</script>

<div class="space-y-6">
	<div class="flex flex-wrap items-center justify-between gap-3">
		<h1 class="text-2xl font-semibold">NPJs</h1>
		<Button href="/plataforma/novo">Novo NPJ</Button>
	</div>

	<form class="flex flex-wrap gap-2" onsubmit={filtrar}>
		<Input class="max-w-xs" placeholder="Nome, sigla ou identificador" bind:value={q} />
		<select
			class="h-9 rounded-md border bg-background px-3 text-sm"
			bind:value={ativo}
			aria-label="Situação"
		>
			<option value="">Todos</option>
			<option value="true">Ativos</option>
			<option value="false">Desativados</option>
		</select>
		<Button type="submit" variant="outline">Filtrar</Button>
	</form>

	<div class="rounded-md border bg-background">
		<Table.Root>
			<Table.Header>
				<Table.Row>
					<Table.Head>Sigla</Table.Head>
					<Table.Head>Nome</Table.Head>
					<Table.Head class="hidden md:table-cell">Identificador</Table.Head>
					<Table.Head>Situação</Table.Head>
				</Table.Row>
			</Table.Header>
			<Table.Body>
				{#each data.tenants as tenant (tenant.id)}
					<Table.Row>
						<Table.Cell class="font-medium">
							<a href="/plataforma/{tenant.id}" class="hover:underline">{tenant.sigla}</a>
						</Table.Cell>
						<Table.Cell>
							{tenant.nome}
							{#if tenant.instituicao}
								<span class="block text-xs text-muted-foreground">{tenant.instituicao}</span>
							{/if}
						</Table.Cell>
						<Table.Cell class="hidden font-mono text-xs md:table-cell">{tenant.slug}</Table.Cell>
						<Table.Cell>
							<Badge variant={tenant.ativo ? 'default' : 'secondary'}>
								{tenant.ativo ? 'Ativo' : 'Desativado'}
							</Badge>
						</Table.Cell>
					</Table.Row>
				{:else}
					<Table.Row>
						<Table.Cell colspan={4} class="text-center text-muted-foreground">
							Nenhum NPJ encontrado.
						</Table.Cell>
					</Table.Row>
				{/each}
			</Table.Body>
		</Table.Root>
	</div>
</div>
