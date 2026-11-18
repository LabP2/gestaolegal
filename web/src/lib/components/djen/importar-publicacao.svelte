<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import * as Select from '$lib/components/ui/select';
	import BaseSelectorDialog from '$lib/components/base-selector-dialog.svelte';
	import type { AcervoItem } from '$lib/types/djen';
	let {
		item,
		ocupado,
		importar
	}: { item: AcervoItem; ocupado: boolean; importar: (id: number | null) => void } = $props();
	let escolha = $state<string | null>(null);
	let manual = $state<{ id: number; nome: string } | null>(null);
	const candidatos = $derived(item.atendidos_sugeridos ?? []);
	const opcoes = $derived(
		manual && !candidatos.some((a) => a.id === manual?.id) ? [...candidatos, manual] : candidatos
	);
	const selecionado = $derived(
		escolha ?? (candidatos.length === 1 ? String(candidatos[0].id) : '')
	);
</script>

<div class="space-y-2 rounded-md border bg-background/70 p-3">
	<p class="text-sm font-medium">Parte para importar</p>
	{#if item.id_processo}
		<p class="text-sm text-muted-foreground">A publicação será vinculada ao processo existente.</p>
	{:else}
		<p class="text-xs text-muted-foreground">
			{candidatos.length === 1
				? 'Atendido sugerido por nome completo ou variação cadastrada. Confirme antes de importar.'
				: candidatos.length > 1
					? 'Mais de um atendido corresponde às partes. Escolha quem associar.'
					: 'Nenhum atendido identificado pelo nome. Escolha uma parte ou importe sem parte.'}
		</p>
		<div class="flex flex-wrap items-center gap-2">
			<Select.Root
				type="single"
				value={selecionado}
				onValueChange={(v) => (escolha = v)}
				disabled={ocupado}
			>
				<Select.Trigger class="w-full sm:w-72" aria-label={`Parte da publicação ${item.id_djen}`}>
					<span class="truncate"
						>{opcoes.find((a) => String(a.id) === selecionado)?.nome ??
							'Sem parte selecionada'}</span
					>
				</Select.Trigger>
				<Select.Content>
					<Select.Item value="sem_parte">Sem parte</Select.Item>
					{#each opcoes as a}<Select.Item value={String(a.id)}>{a.nome} · #{a.id}</Select.Item
						>{/each}
				</Select.Content>
			</Select.Root>
			{#if !ocupado}
				<BaseSelectorDialog
					apiEndpoint="atendido"
					dialogTitle="Escolher parte da publicação"
					dialogDescription="Selecione um atendido da unidade para associar ao processo."
					buttonText="Escolher outro atendido"
					emptyStateText="Nenhum atendido encontrado"
					searchPlaceholder="Buscar por nome ou CPF"
					multiSelect={false}
					onSelect={(itens) => {
						manual = itens[0] ?? null;
						escolha = manual ? String(manual.id) : 'sem_parte';
					}}
				/>
			{/if}
		</div>
	{/if}
	<Button
		disabled={ocupado}
		onclick={() =>
			importar(
				item.id_processo || !selecionado || selecionado === 'sem_parte' ? null : Number(selecionado)
			)}
	>
		{item.id_processo
			? 'Importar publicação'
			: selecionado && selecionado !== 'sem_parte'
				? 'Confirmar parte e importar'
				: 'Importar sem parte'}
	</Button>
</div>
