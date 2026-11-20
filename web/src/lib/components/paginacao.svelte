<script lang="ts">
	import { goto } from '$app/navigation';
	import { page as pagina } from '$app/state';
	import { Button } from '#lib/components/ui/button/index.ts';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import ChevronsLeft from '@lucide/svelte/icons/chevrons-left';
	import ChevronsRight from '@lucide/svelte/icons/chevrons-right';
	let {
		total,
		page,
		per_page,
		disabled = false,
		tamanhos = false,
		onPageChange,
		onPageSizeChange
	}: {
		total: number;
		page: number;
		per_page: number;
		disabled?: boolean;
		tamanhos?: boolean;
		onPageChange?: (n: number) => void | Promise<void>;
		onPageSizeChange?: (n: number) => void | Promise<void>;
	} = $props();
	const paginas = $derived(Math.max(1, Math.ceil(total / per_page)));
	async function navegar(n: number) {
		if (onPageChange) return onPageChange(n);
		const params = new URLSearchParams(pagina.url.search);
		params.set('page', String(n));
		await goto(`?${params}`, { reset: false });
	}
	async function tamanho(n: number) {
		if (onPageSizeChange) return onPageSizeChange(n);
		const params = new URLSearchParams(pagina.url.search);
		params.set('per_page', String(n));
		params.delete('page');
		await goto(`?${params}`, { reset: false });
	}
</script>

<nav
	aria-label="Paginação"
	class="flex flex-wrap items-center justify-between gap-3 rounded-md border bg-muted/50 px-4 py-3 text-sm"
>
	<p class="text-muted-foreground">
		Mostrando{' '}<strong>{total ? (page - 1) * per_page + 1 : 0}</strong>{' '}a{' '}
		<strong>{Math.min(page * per_page, total)}</strong>{' '}de{' '}
		<strong>{total}</strong>{' '}resultados
	</p>
	<div class="flex flex-wrap items-center gap-3">
		{#if tamanhos}<label class="flex items-center gap-2">
				Por página
				<select
					aria-label="Resultados por página"
					class="h-9 min-w-20 rounded-md border bg-background pr-8 pl-2"
					value={per_page}
					{disabled}
					onchange={(e) => tamanho(Number(e.currentTarget.value))}
				>
					{#each [...new Set([20, 50, 100, per_page])].sort((a, b) => a - b) as n}<option value={n}>
							{n}
						</option>{/each}
				</select>
			</label>{/if}
		<span class="text-muted-foreground">Página {page} de {paginas}</span>
		<div class="flex items-center gap-1">
			<Button
				variant="ghost"
				size="icon"
				title="Primeira página"
				aria-label="Primeira página"
				disabled={disabled || page <= 1}
				onclick={() => navegar(1)}
			>
				<ChevronsLeft class="size-4" />
			</Button>
			<Button
				variant="ghost"
				size="icon"
				title="Página anterior"
				aria-label="Página anterior"
				disabled={disabled || page <= 1}
				onclick={() => navegar(page - 1)}
			>
				<ChevronLeft class="size-4" />
			</Button>
			<Button
				variant="ghost"
				size="icon"
				title="Próxima página"
				aria-label="Próxima página"
				disabled={disabled || page >= paginas}
				onclick={() => navegar(page + 1)}
			>
				<ChevronRight class="size-4" />
			</Button>
			<Button
				variant="ghost"
				size="icon"
				title="Última página"
				aria-label="Última página"
				disabled={disabled || page >= paginas}
				onclick={() => navegar(paginas)}
			>
				<ChevronsRight class="size-4" />
			</Button>
		</div>
	</div>
</nav>
