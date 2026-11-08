<script lang="ts">
	import type { StatusDjen } from '$lib/types';
	import { formatDateTime } from '$lib/utils/date';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';

	let { status }: { status: StatusDjen } = $props();
</script>

<div
	class="flex flex-wrap items-center gap-2 rounded-md border px-4 py-2 text-sm {status.atrasada
		? 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100'
		: 'bg-muted/40 text-muted-foreground'}"
	role="status"
>
	{#if status.atrasada}
		<TriangleAlert class="h-4 w-4" />
	{/if}
	{#if status.ultima}
		<span>
			Última sincronização: {formatDateTime(status.ultima.fim ?? status.ultima.inicio)}
			{#if status.ultima.status !== 'ok'}
				({status.ultima.status === 'parcial' ? 'parcial' : 'com erro'})
			{/if}
		</span>
		{#if status.atrasada}
			<span>— mais de 2 dias úteis sem sincronizar; a rotina pode ter parado.</span>
		{/if}
	{:else}
		<span>A rotina do DJEN ainda não rodou para este NPJ.</span>
	{/if}
</div>
