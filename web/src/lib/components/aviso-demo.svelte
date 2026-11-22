<script lang="ts">
	import { onMount } from 'svelte';
	import FlaskConical from '@lucide/svelte/icons/flask-conical';
	import { ambienteDemo } from '#lib/stores/ambiente.ts';

	/** `cartao` na tela de login; `faixa` no topo do painel. */
	let { variante = 'faixa' }: { variante?: 'cartao' | 'faixa' } = $props();

	const MENSAGEM =
		'os dados são apagados todos os dias à 0h. Não envie documentos nem dados reais.';

	let demo = $state(false);

	onMount(() => {
		ambienteDemo().then((valor) => (demo = valor));
	});
</script>

{#if demo}
	<div
		role="note"
		aria-label="Ambiente de demonstração"
		data-testid="aviso-demo"
		class={variante === 'cartao'
			? 'flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50/95 p-4 text-sm text-amber-950 shadow-lg'
			: 'flex items-center justify-center gap-2 border-b border-amber-300 bg-amber-100 px-4 py-1.5 text-center text-xs text-amber-950'}
	>
		<FlaskConical class="h-4 w-4 shrink-0" aria-hidden="true" />
		<p><strong>Ambiente de demonstração:</strong> {MENSAGEM}</p>
	</div>
{/if}
