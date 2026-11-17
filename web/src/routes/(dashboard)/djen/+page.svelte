<script lang="ts">
	import Acervo from '$lib/components/djen/acervo.svelte';
	import ListaPublicacoes from '$lib/components/djen/lista-publicacoes.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

{#if data.acervo}
	<Acervo dados={data.acervo} />
{:else}
	<ListaPublicacoes
		titulo="Publicações do DJEN"
		publicacoes={data.publicacoes}
		status={data.status}
		urole={data.me.urole}
	/>
{/if}
