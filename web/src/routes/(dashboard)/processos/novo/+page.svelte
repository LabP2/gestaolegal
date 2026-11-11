<script lang="ts">
	import ProcessoForm from '$lib/forms/processo-form.svelte';
	import PartesEditor, { type ParteEditavel } from '$lib/components/processos/partes-editor.svelte';
	import { Button } from '$lib/components/ui/button';
	import { api } from '$lib/api-client';
	import { goto } from '$app/navigation';
	import { ApiException, type Processo } from '$lib/types';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	let partes = $state<ParteEditavel[]>([]);

	async function salvar(dados: Record<string, unknown>) {
		if (partes.length === 0) {
			throw new ApiException('Informe pelo menos uma parte do processo', 'VALIDATION_ERROR');
		}
		return api.post<Processo>('processos', {
			...dados,
			partes: partes.map((p) => ({ id_atendido: p.id_atendido, polo: p.polo }))
		});
	}
</script>

<div class="min-h-screen bg-background">
	<div class="mb-8 flex flex-wrap items-center justify-between gap-4">
		<div>
			<h1 class="text-3xl font-bold tracking-tight text-foreground">Novo processo sem caso</h1>
			<p class="mt-2 text-muted-foreground">
				Processo acompanhado sem abrir caso (ex.: Procuradoria). Com número CNJ, a rotina do DJEN
				busca o histórico de publicações.
			</p>
		</div>
		<Button variant="outline" href="/processos">Voltar</Button>
	</div>

	<ProcessoForm
		data={data.form}
		{salvar}
		onUpdate={(processo) => goto(`/processos/${processo.id}`)}
		onCancel={() => goto('/processos')}
	>
		{#snippet extra()}
			<PartesEditor bind:partes />
		{/snippet}
	</ProcessoForm>
</div>
