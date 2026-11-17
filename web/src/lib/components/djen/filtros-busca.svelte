<script lang="ts">
	import DateRangePicker from '$lib/components/date-range-picker.svelte';
	import UnidadeSelector from '$lib/components/unidade-selector.svelte';
	import * as Select from '$lib/components/ui/select';
	import { Button } from '$lib/components/ui/button';
	import { TRIBUNAIS_DJEN } from '$lib/utils/tribunais-djen';
	import { BUSCA_PARTE_MAX_DIAS, type Unidade } from '$lib/types';
	let {
		de = $bindable(''),
		ate = $bindable(''),
		tribunais = $bindable<string[]>([]),
		unidades = [],
		id = 'monitoramento-periodo',
		exigirTribunalMonitoramento = false,
		erroTribunais = false
	}: {
		de: string;
		ate: string;
		tribunais: string[];
		unidades?: Unidade[];
		id?: string;
		exigirTribunalMonitoramento?: boolean;
		erroTribunais?: boolean;
	} = $props();
</script>

<div>
	<span class="mb-1 block text-sm font-medium">Unidade ativa</span>
	<div class="flex h-9 items-center"><UnidadeSelector {unidades} /></div>
</div>
<div>
	<label for={id} class="mb-1 block text-sm font-medium">Período</label>
	<DateRangePicker {id} bind:de bind:ate maxDias={BUSCA_PARTE_MAX_DIAS} />
</div>
<div>
	<span class="mb-1 block text-sm font-medium">Tribunais</span>
	<Select.Root type="multiple" bind:value={tribunais}>
		<Select.Trigger
			class="w-56"
			aria-label="Tribunais"
			aria-invalid={erroTribunais || undefined}
			aria-describedby={exigirTribunalMonitoramento ? `${id}-tribunais-ajuda` : undefined}
			><span class="truncate"
				>{tribunais.length === 0
					? exigirTribunalMonitoramento
						? 'Todos (busca manual)'
						: 'Todos'
					: tribunais.length <= 3
						? tribunais.join(', ')
						: `${tribunais.length} tribunais`}</span
			></Select.Trigger
		>
		<Select.Content class="max-h-80">
			{#each TRIBUNAIS_DJEN as grupo (grupo.grupo)}<Select.Group
					><Select.GroupHeading>{grupo.grupo}</Select.GroupHeading
					>{#each grupo.siglas as sigla (sigla)}<Select.Item value={sigla}>{sigla}</Select.Item
						>{/each}</Select.Group
				>{/each}
		</Select.Content>
	</Select.Root>
	{#if exigirTribunalMonitoramento}
		<p
			id={`${id}-tribunais-ajuda`}
			role={erroTribunais ? 'alert' : undefined}
			class={`mt-1 max-w-56 text-xs ${erroTribunais ? 'text-destructive' : 'text-muted-foreground'}`}
		>
			Para monitorar por nome, selecione ao menos um tribunal.
		</p>
	{/if}
</div>
{#if tribunais.length}<Button
		type="button"
		variant="ghost"
		size="sm"
		onclick={() => (tribunais = [])}>Limpar tribunais</Button
	>{/if}
