<script lang="ts">
	import { Button } from '#lib/components/ui/button/index.ts';
	import * as Tooltip from '#lib/components/ui/tooltip/index.ts';
	let {
		texto,
		label = texto,
		motivo = '',
		onclick
	}: { texto: string; label?: string; motivo?: string; onclick: () => void } = $props();
</script>

<Tooltip.Root disabled={!motivo}>
	<Tooltip.Trigger>
		{#snippet child({ props })}
			<Button
				{...props}
				variant="outline"
				class={motivo ? 'cursor-not-allowed opacity-50 aria-disabled:pointer-events-auto' : ''}
				aria-disabled={!!motivo}
				aria-label={label}
				onclick={() => {
					if (!motivo) onclick();
				}}
			>
				{texto}
			</Button>
		{/snippet}
	</Tooltip.Trigger>
	<Tooltip.Content role="tooltip">{motivo}</Tooltip.Content>
</Tooltip.Root>
