<script lang="ts">
	import BancoExemplos from '$lib/components/djen/banco-exemplos.svelte';
	import Acervo from '$lib/components/djen/acervo.svelte';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
</script>

<Acervo dados={data.acervo} treino />

{#if data.me.urole === 'admin'}
	<div class="mt-6">
		<BancoExemplos />
	</div>
{/if}
