<script lang="ts">
	import ProcessoForm from '$lib/forms/processo-form.svelte';
	import PartesEditor, { type ParteEditavel } from '$lib/components/processos/partes-editor.svelte';
	import { Button } from '$lib/components/ui/button';
	import { api } from '$lib/api-client';
	import { goto } from '$app/navigation';
	import { ApiException, type Processo } from '$lib/types';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	// svelte-ignore state_referenced_locally
	const { processo } = data;

	let partes = $state<ParteEditavel[]>(
		processo.partes.map((p) => ({
			id_atendido: p.id_atendido,
			nome: p.nome,
			polo: p.polo,
			sem_triagem: p.sem_triagem
		}))
	);

	async function salvar(dados: Record<string, unknown>) {
		if (partes.length === 0) {
			throw new ApiException('Informe pelo menos uma parte do processo', 'VALIDATION_ERROR');
		}
		return api.put<Processo>(`processos/${processo.id}`, {
			...dados,
			partes: partes.map((p) => ({ id_atendido: p.id_atendido, polo: p.polo }))
		});
	}
</script>

<div class="min-h-screen bg-background">
	<div class="mb-8 flex flex-wrap items-center justify-between gap-4">
		<div>
			<h1 class="text-3xl font-bold tracking-tight text-foreground">
				Editar processo {processo.numero || `#${processo.id}`}
			</h1>
			<p class="mt-2 text-muted-foreground">Processo sem caso</p>
		</div>
		<Button variant="outline" href="/processos/{processo.id}">Voltar</Button>
	</div>

	<ProcessoForm
		data={data.form}
		isCreateMode={false}
		{salvar}
		onUpdate={() => goto(`/processos/${processo.id}`)}
		onCancel={() => goto(`/processos/${processo.id}`)}
	>
		{#snippet extra()}
			<PartesEditor bind:partes />
		{/snippet}
	</ProcessoForm>
</div>
