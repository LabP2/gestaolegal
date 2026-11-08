<script lang="ts">
	import { goto } from '$app/navigation';
	import { Button } from '$lib/components/ui/button';
	import { sairDaPlataforma, PLATAFORMA_LOGIN } from '$lib/plataforma-client';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: import('svelte').Snippet } = $props();

	function sair() {
		sairDaPlataforma();
		goto(PLATAFORMA_LOGIN);
	}
</script>

<svelte:head>
	<title>Plataforma · Gestão Legal</title>
</svelte:head>

<div class="min-h-screen bg-muted/30">
	{#if data.admin}
		<header class="border-b bg-background">
			<div class="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
				<a href="/plataforma" class="font-semibold">
					Gestão Legal <span class="font-normal text-muted-foreground">· Plataforma</span>
				</a>
				<div class="flex items-center gap-3 text-sm">
					<span class="hidden text-muted-foreground sm:inline">{data.admin.email}</span>
					<Button variant="outline" size="sm" onclick={sair}>Sair</Button>
				</div>
			</div>
		</header>
	{/if}
	<main class="mx-auto max-w-5xl px-4 py-8">
		{@render children()}
	</main>
</div>
