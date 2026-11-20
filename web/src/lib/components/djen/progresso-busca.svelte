<script lang="ts">
	let { detalhe = 'Consultando publicações e salvando os resultados.' }: { detalhe?: string } =
		$props();
</script>

<div
	class="fixed right-4 bottom-6 left-4 z-50 space-y-3 rounded-lg border bg-card p-4 shadow-lg sm:left-auto sm:w-96"
	role="status"
	aria-live="polite"
>
	<div>
		<p class="font-medium">Buscando no DJEN…</p>
		<p class="mt-1 text-sm text-muted-foreground">{detalhe}</p>
	</div>
	<div
		class="h-2 overflow-hidden rounded-full bg-muted"
		role="progressbar"
		aria-label="Busca no DJEN em andamento"
		aria-valuetext="Aguardando a conclusão da consulta"
	>
		<div class="barra h-full w-1/3 rounded-full bg-primary"></div>
	</div>
	<p class="text-xs text-muted-foreground">Aguarde a conclusão para sair desta página.</p>
</div>

<style>
	.barra {
		animation: busca 1.4s ease-in-out infinite alternate;
	}
	@keyframes busca {
		from {
			transform: translateX(0);
		}
		to {
			transform: translateX(200%);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.barra {
			animation: none;
			width: 100%;
			opacity: 0.6;
		}
	}
</style>
