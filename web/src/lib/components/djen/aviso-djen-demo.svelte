<script lang="ts">
	import { onMount } from 'svelte';
	import FlaskConical from '@lucide/svelte/icons/flask-conical';
	import { ambienteDemo } from '#lib/stores/ambiente.ts';

	const MENSAGEM =
		'as publicações do DJEN são fictícias e a consulta ao DJEN real está desativada. Buscas por processos ou OABs reais não trazem resultados.';

	let demo = $state(false);

	onMount(() => {
		ambienteDemo().then((valor) => (demo = valor));
	});
</script>

{#if demo}
	<div
		role="note"
		data-testid="aviso-djen-demo"
		class="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950"
	>
		<FlaskConical class="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
		<p><strong>Demonstração:</strong> {MENSAGEM}</p>
	</div>
{/if}
