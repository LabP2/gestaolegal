<script lang="ts">
	import BancoExemplos from '$lib/components/djen/banco-exemplos.svelte';
	import ListaPublicacoes from '$lib/components/djen/lista-publicacoes.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<ListaPublicacoes
	titulo="Publicações do DJEN"
	publicacoes={data.publicacoes}
	status={data.status}
	urole={data.me.urole}
/>

{#if data.me.urole === 'admin'}
	<div class="mt-6">
		<BancoExemplos />
	</div>
{/if}
