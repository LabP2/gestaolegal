<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Eye from '@lucide/svelte/icons/eye';
	import { api } from '$lib/api-client';
	import {
		ApiException,
		DJEN_PAPEIS_GESTAO,
		type BuscaProcessoDjen,
		type Me,
		type PublicacaoListItem
	} from '$lib/types';
	import { formatDateOnly, formatDateTime } from '$lib/utils/date';
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	/**
	 * Card "Publicações no DJEN" da tela do processo, com ou sem caso. Só
	 * aparece com o DJEN ligado para o NPJ (docs/plano-djen.md, §6).
	 */
	let {
		processo,
		me,
		class: className = ''
	}: {
		processo: {
			id: number;
			numero_cnj?: string | null;
			djen_pendente?: boolean;
			djen_consultado_em?: string | null;
		};
		me: Me;
		class?: string;
	} = $props();

	const djenAtivo = $derived(me.tenant?.djen_ativo === true);
	// Botão só para quem pode vincular (plano, §6–7).
	const podeBuscarDjen = $derived(djenAtivo && DJEN_PAPEIS_GESTAO.includes(me.urole));
	// svelte-ignore state_referenced_locally
	let djenConsultadoEm = $state(processo.djen_consultado_em ?? null);
	let buscandoDjen = $state(false);

	let publicacoes = $state<PublicacaoListItem[]>([]);
	let totalPublicacoes = $state(0);
	let carregandoPublicacoes = $state(false);

	async function carregarPublicacoes() {
		if (!djenAtivo || !processo.numero_cnj) return;
		carregandoPublicacoes = true;
		try {
			const params = new URLSearchParams({ q: processo.numero_cnj, per_page: '50' });
			const r = await api.get<{ items: PublicacaoListItem[]; total: number }>(
				`djen/publicacoes?${params}`
			);
			publicacoes = r.items;
			totalPublicacoes = r.total;
		} catch (err) {
			toast.error(err instanceof ApiException ? err.message : 'Erro ao carregar as publicações.');
		} finally {
			carregandoPublicacoes = false;
		}
	}

	onMount(carregarPublicacoes);

	const situacaoBadge: Record<
		string,
		{ text: string; variant: 'default' | 'outline' | 'secondary' | 'destructive' }
	> = {
		vinculada: { text: 'Vinculada', variant: 'default' },
		pendente: { text: 'Sem caso', variant: 'outline' },
		descartada: { text: 'Descartada', variant: 'secondary' },
		cancelada: { text: 'Cancelada no DJEN', variant: 'destructive' }
	};

	async function buscarDjen() {
		buscandoDjen = true;
		try {
			const r = await api.post<BuscaProcessoDjen>(`processos/${processo.id}/djen/buscar`);
			djenConsultadoEm = r.djen_consultado_em;
			await carregarPublicacoes();
			toast.success(
				r.novas ? `${r.novas} publicação(ões) nova(s) no DJEN.` : 'Nenhuma publicação nova no DJEN.'
			);
		} catch (err) {
			toast.error(err instanceof ApiException ? err.message : 'Erro ao consultar o DJEN.');
		} finally {
			buscandoDjen = false;
		}
	}
</script>

{#if djenAtivo}
	<Card.Root class={className}>
		<Card.Header>
			<Card.Title>Publicações no DJEN</Card.Title>
			<Card.Description>
				{#if !processo.numero_cnj}
					O número do processo não está no padrão CNJ (20 dígitos); as publicações não são buscadas.
				{:else if djenConsultadoEm}
					Última consulta: {formatDateTime(djenConsultadoEm)}.
				{:else if processo.djen_pendente}
					Aguardando a rotina buscar o histórico de publicações.
				{:else}
					Ainda não consultado.
				{/if}
			</Card.Description>
		</Card.Header>
		<Card.Content class="space-y-4">
			<div class="flex flex-wrap gap-2">
				{#if podeBuscarDjen && processo.numero_cnj}
					<Button variant="outline" onclick={buscarDjen} disabled={buscandoDjen}>
						<RefreshCw class="mr-2 h-4 w-4 {buscandoDjen ? 'animate-spin' : ''}" />
						{buscandoDjen ? 'Buscando…' : 'Buscar publicações agora'}
					</Button>
				{/if}
				{#if totalPublicacoes > publicacoes.length}
					<Button variant="ghost" href="/djen?q={processo.numero_cnj ?? ''}">
						Ver todas ({totalPublicacoes})
					</Button>
				{/if}
			</div>

			{#if processo.numero_cnj}
				{#if carregandoPublicacoes && publicacoes.length === 0}
					<p class="text-sm text-muted-foreground">Carregando publicações…</p>
				{:else if publicacoes.length === 0}
					<p class="text-sm text-muted-foreground">Nenhuma publicação encontrada.</p>
				{:else}
					<ul class="divide-y rounded-lg border">
						{#each publicacoes as p (p.id)}
							{@const badge = situacaoBadge[p.ativo ? p.situacao : 'cancelada']}
							<li class="flex items-start justify-between gap-3 p-3">
								<a href="/djen/publicacoes/{p.id}" class="min-w-0 flex-1 space-y-1">
									<div class="flex flex-wrap items-center gap-2 text-sm">
										<span class="font-medium">{formatDateOnly(p.data_disponibilizacao)}</span>
										{#if p.tipo_comunicacao}<span>{p.tipo_comunicacao}</span>{/if}
										{#if p.tipo_documento}
											<span class="text-muted-foreground">· {p.tipo_documento}</span>
										{/if}
										{#if badge}<Badge variant={badge.variant}>{badge.text}</Badge>{/if}
									</div>
									{#if p.nome_orgao}
										<p class="truncate text-xs text-muted-foreground">
											{p.sigla_tribunal ? `${p.sigla_tribunal} · ` : ''}{p.nome_orgao}
										</p>
									{/if}
									{#if p.resumo}
										<p class="line-clamp-2 text-sm text-muted-foreground">{p.resumo}</p>
									{/if}
								</a>
								<Button
									variant="ghost"
									size="sm"
									href="/djen/publicacoes/{p.id}"
									title="Ver publicação"
								>
									<Eye class="h-4 w-4" />
								</Button>
							</li>
						{/each}
					</ul>
				{/if}
			{/if}
		</Card.Content>
	</Card.Root>
{/if}
