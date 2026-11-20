<script lang="ts">
	import DetalhePublicacao from '#lib/components/djen/detalhe-publicacao.svelte';
	import { Button } from '#lib/components/ui/button/index.ts';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
	const publicacao = $derived(data.publicacao);
</script>

<DetalhePublicacao
	{publicacao}
	textoPlano={publicacao.texto_plano}
	historico={publicacao.historico}
	voltar={data.voltar}
>
	{#snippet acoes()}
		{#if publicacao.comunicacao_id}
			<Button variant="outline" href={`/djen/publicacoes/${publicacao.comunicacao_id}`}>
				Abrir operação
			</Button>
		{/if}
	{/snippet}
</DetalhePublicacao>
