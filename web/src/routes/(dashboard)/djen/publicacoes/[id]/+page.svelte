<script lang="ts">
	import VincularPublicacao from '$lib/components/djen/vincular-publicacao.svelte';
	import { invalidateAll } from '$app/navigation';
	import ConfirmAction from '$lib/components/confirm-action.svelte';
	import { api } from '$lib/api-client';
	import { mensagemDeErro } from '$lib/utils/erros';
	import { toast } from 'svelte-sonner';
	import DetalhePublicacao from '$lib/components/djen/detalhe-publicacao.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const publicacao = $derived(data.publicacao);

	async function descartar() {
		try {
			await api.post(`djen/publicacoes/${publicacao.id}/descartar`);
			toast.success('Publicação descartada');
			await invalidateAll();
		} catch (err) {
			toast.error(mensagemDeErro(err, 'Não foi possível descartar a publicação.'));
		}
	}
</script>

<DetalhePublicacao
	{publicacao}
	voltar={publicacao.situacao === 'pendente' && publicacao.pode_vincular
		? '/djen?situacao=pendente'
		: '/djen'}
>
	{#snippet acoes()}
		{#if publicacao.pode_vincular && publicacao.situacao !== 'vinculada'}
			<VincularPublicacao {publicacao} onVinculada={() => invalidateAll()} />
		{/if}
		{#if publicacao.pode_vincular && publicacao.situacao === 'pendente'}
			<ConfirmAction
				title="Descartar esta publicação?"
				description="A publicação será descartada e permanecerá no acervo. Para avaliar relevância, use o contexto na tela de treino."
				confirmText="Descartar"
				cancelText="Voltar"
				triggerText="Descartar"
				buttonSize="default"
				onConfirm={descartar}
			/>
		{/if}
	{/snippet}
</DetalhePublicacao>
