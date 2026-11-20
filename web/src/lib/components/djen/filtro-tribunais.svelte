<script lang="ts">
	import * as Select from '#lib/components/ui/select/index.ts';
	import { TRIBUNAIS_DJEN } from '#lib/utils/tribunais-djen.ts';
	let {
		value = $bindable<string[]>([]),
		disabled = false,
		onchange
	}: { value?: string[]; disabled?: boolean; onchange: () => void } = $props();
</script>

<div class="space-y-1">
	<span class="block text-sm font-medium">Tribunais</span>
	<Select.Root type="multiple" bind:value {disabled} onValueChange={onchange}>
		<Select.Trigger class="w-full" aria-label="Tribunais">
			<span class="truncate" title={value.join(', ')}>
				{value.length ? value.join(', ') : 'Todos os tribunais'}
			</span>
		</Select.Trigger>
		<Select.Content class="max-h-80 w-56">
			{#each TRIBUNAIS_DJEN as grupo (grupo.grupo)}
				<Select.Group>
					<Select.GroupHeading>{grupo.grupo}</Select.GroupHeading>
					{#each grupo.siglas as sigla (sigla)}<Select.Item value={sigla}>
							{sigla}
						</Select.Item>{/each}
				</Select.Group>
			{/each}
		</Select.Content>
	</Select.Root>
</div>
