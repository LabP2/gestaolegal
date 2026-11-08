<script lang="ts">
	import ListaPublicacoes from '$lib/components/djen/lista-publicacoes.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<ListaPublicacoes
	titulo="Publicações sem caso"
	descricao="Chegaram pelas OABs monitoradas e não casaram com nenhum processo cadastrado. Vincule a um processo ou descarte as que não são do NPJ. Pendentes há mais de 90 dias são apagadas pela rotina."
	publicacoes={data.publicacoes}
	status={data.status}
	urole={data.me.urole}
	situacaoFixa="pendente"
/>
