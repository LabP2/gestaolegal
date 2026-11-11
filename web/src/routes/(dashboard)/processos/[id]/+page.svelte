<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import InfoCard from '$lib/components/ui/info-card.svelte';
	import ConfirmAction from '$lib/components/confirm-action.svelte';
	import PublicacoesProcesso from '$lib/components/djen/publicacoes-processo.svelte';
	import { api } from '$lib/api-client';
	import { goto, invalidateAll } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { mensagemDeErro } from '$lib/utils/erros';
	import { POLO_PARTE_LABEL, PROCESSO_PAPEIS_SEM_CASO } from '$lib/types';
	import Edit from '@lucide/svelte/icons/edit';
	import Briefcase from '@lucide/svelte/icons/briefcase';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const processo = $derived(data.processo);
	const me = $derived(data.me);

	const semCaso = $derived(processo.id_caso === null);
	// Mesma régua da API: processo de caso só o admin inativa; sem caso, a gestão da unidade.
	const podeInativar = $derived(
		processo.status &&
			(semCaso ? PROCESSO_PAPEIS_SEM_CASO.includes(me.urole) : me.urole === 'admin')
	);
	const linkEditar = $derived(
		semCaso
			? `/processos/${processo.id}/editar`
			: `/casos/${processo.id_caso}/processos/${processo.id}/editar`
	);

	function formatDate(valor?: string | null): string {
		if (!valor) return 'Não informado';
		// Datas de calendário: UTC evita o deslocamento de um dia.
		return new Date(valor).toLocaleDateString('pt-BR', { timeZone: 'UTC' });
	}

	function formatCurrency(valor?: number | null): string {
		if (valor === null || valor === undefined) return 'Não informado';
		return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(valor);
	}

	const info = $derived([
		{ label: 'Espécie', value: processo.especie },
		{ label: 'Número', value: processo.numero || 'Não informado' },
		...(processo.vara ? [{ label: 'Vara', value: processo.vara }] : []),
		...(processo.probabilidade ? [{ label: 'Probabilidade', value: processo.probabilidade }] : []),
		...(processo.posicao_assistido
			? [{ label: 'Posição do assistido', value: processo.posicao_assistido }]
			: []),
		{ label: 'Status', value: processo.status ? 'Ativo' : 'Inativo' }
	]);

	const datas = $derived([
		{ label: 'Distribuição', value: formatDate(processo.data_distribuicao) },
		{ label: 'Trânsito em julgado', value: formatDate(processo.data_transito_em_julgado) },
		{ label: 'Valor da causa inicial', value: formatCurrency(processo.valor_causa_inicial) },
		{ label: 'Valor da causa atual', value: formatCurrency(processo.valor_causa_atual) }
	]);

	async function inativar() {
		try {
			await api.delete(`processos/${processo.id}`);
			toast.success('Processo inativado');
			await invalidateAll();
		} catch (err) {
			toast.error(mensagemDeErro(err, 'Não foi possível inativar o processo.'));
		}
	}
</script>

<div class="space-y-6">
	<div class="flex flex-wrap items-center justify-between gap-4">
		<div class="min-w-0">
			<div class="flex flex-wrap items-center gap-3">
				<h1 class="text-3xl font-bold tracking-tight break-all">
					{processo.numero || processo.identificacao || `Processo #${processo.id}`}
				</h1>
				<Badge variant={processo.status ? 'default' : 'secondary'}>
					{processo.status ? 'Ativo' : 'Inativo'}
				</Badge>
				{#if semCaso}
					<Badge variant="outline">Sem caso</Badge>
				{/if}
			</div>
			{#if processo.identificacao && processo.numero}
				<p class="mt-1 text-muted-foreground">{processo.identificacao}</p>
			{/if}
			{#if processo.link}
				<a
					href={processo.link}
					target="_blank"
					rel="noopener noreferrer"
					class="text-sm break-all text-primary hover:underline"
				>
					{processo.link}
				</a>
			{/if}
		</div>
		<div class="flex flex-wrap gap-2">
			<Button variant="outline" onclick={() => history.back()}>Voltar</Button>
			{#if !semCaso}
				<Button variant="outline" href="/casos/{processo.id_caso}">
					<Briefcase class="mr-2 h-4 w-4" />
					Caso #{processo.id_caso}
				</Button>
			{/if}
			{#if podeInativar}
				<ConfirmAction
					title="Inativar processo?"
					description="O processo sai da lista de ativos. As publicações do DJEN continuam vinculadas."
					confirmText="Inativar"
					triggerText="Inativar"
					buttonSize="default"
					onConfirm={inativar}
				/>
			{/if}
			<Button href={linkEditar}>
				<Edit class="mr-2 h-4 w-4" />
				Editar
			</Button>
		</div>
	</div>

	<div class="grid gap-6 md:grid-cols-2">
		<InfoCard title="Informações do processo" items={info} />
		<InfoCard title="Datas e valores" items={datas} />

		<Card.Root class="md:col-span-2">
			<Card.Header>
				<Card.Title>Partes</Card.Title>
				{#if !semCaso}
					<Card.Description>Atendidos do caso #{processo.id_caso}.</Card.Description>
				{/if}
			</Card.Header>
			<Card.Content>
				{#if processo.partes.length === 0}
					<p class="text-sm text-muted-foreground">Nenhuma parte.</p>
				{:else}
					<ul class="divide-y">
						{#each processo.partes as parte (parte.id_atendido)}
							<li class="flex flex-wrap items-center gap-2 py-2">
								<a
									href="/plantao/atendidos-assistidos/{parte.id_atendido}"
									class="font-medium hover:underline"
								>
									{parte.nome}
								</a>
								{#if parte.polo}
									<Badge variant="outline">{POLO_PARTE_LABEL[parte.polo]}</Badge>
								{/if}
								{#if parte.sem_triagem}
									<Badge variant="secondary">Sem triagem</Badge>
								{/if}
							</li>
						{/each}
					</ul>
				{/if}
			</Card.Content>
		</Card.Root>

		<PublicacoesProcesso {processo} {me} class="md:col-span-2" />

		{#if processo.obs}
			<Card.Root class="md:col-span-2">
				<Card.Header>
					<Card.Title>Observações</Card.Title>
				</Card.Header>
				<Card.Content>
					<p class="text-sm whitespace-pre-wrap">{processo.obs}</p>
				</Card.Content>
			</Card.Root>
		{/if}
	</div>
</div>
