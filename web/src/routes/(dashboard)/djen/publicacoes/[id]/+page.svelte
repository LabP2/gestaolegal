<script lang="ts">
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { SITUACAO_PUBLICACAO_LABEL } from '$lib/types';
	import { formatDateOnly, formatDateTime } from '$lib/utils/date';
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const publicacao = $derived(data.publicacao);

	const POLOS: Record<string, string> = { A: 'Polo ativo', P: 'Polo passivo' };

	const destinatariosPorPolo = $derived(
		Object.entries(
			publicacao.destinatarios.reduce<Record<string, string[]>>((acc, d) => {
				const polo = POLOS[d.polo ?? ''] ?? 'Outros';
				(acc[polo] ??= []).push(d.nome ?? '—');
				return acc;
			}, {})
		)
	);
</script>

<div class="space-y-6">
	<div class="flex flex-wrap items-start justify-between gap-4">
		<div class="space-y-1">
			<div class="flex flex-wrap items-center gap-2">
				<h1 class="text-2xl font-bold tracking-tight">
					{publicacao.tipo_comunicacao ?? 'Publicação'}
					{#if publicacao.tipo_documento}
						<span class="text-muted-foreground">· {publicacao.tipo_documento}</span>
					{/if}
				</h1>
				<Badge variant={publicacao.situacao === 'vinculada' ? 'default' : 'outline'}>
					{SITUACAO_PUBLICACAO_LABEL[publicacao.situacao]}
				</Badge>
				{#if !publicacao.ativo}
					<Badge variant="destructive">Cancelada no DJEN</Badge>
				{/if}
			</div>
			<p class="font-mono text-sm">
				{publicacao.numero_processo_mascara ?? publicacao.numero_processo}
			</p>
			<p class="text-sm text-muted-foreground">
				{formatDateOnly(publicacao.data_disponibilizacao)} · {publicacao.sigla_tribunal ?? '—'}
				· {publicacao.nome_orgao ?? '—'}
				{#if publicacao.nome_classe}· {publicacao.nome_classe}{/if}
			</p>
		</div>
		<div class="flex flex-wrap gap-2">
			<Button variant="outline" href="/djen">Voltar</Button>
			{#if publicacao.id_caso}
				<Button variant="outline" href="/casos/{publicacao.id_caso}">Abrir caso</Button>
			{/if}
		</div>
	</div>

	{#if !publicacao.ativo && publicacao.motivo_cancelamento}
		<p class="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-2 text-sm">
			Motivo do cancelamento: {publicacao.motivo_cancelamento}
		</p>
	{/if}

	<div class="grid gap-6 lg:grid-cols-3">
		<Card.Root class="lg:col-span-2">
			<Card.Header>
				<Card.Title class="text-base">Texto da publicação</Card.Title>
			</Card.Header>
			<Card.Content>
				<!-- Só o HTML filtrado no backend (nh3); o original nunca chega aqui. -->
				<div class="publicacao-djen text-sm leading-relaxed">
					<!-- eslint-disable-next-line svelte/no-at-html-tags -->
					{@html publicacao.texto_html_seguro}
				</div>
			</Card.Content>
		</Card.Root>

		<div class="space-y-6">
			<Card.Root>
				<Card.Header>
					<Card.Title class="text-base">Destinatários</Card.Title>
				</Card.Header>
				<Card.Content class="space-y-3 text-sm">
					{#each destinatariosPorPolo as [polo, nomes] (polo)}
						<div>
							<p class="text-muted-foreground">{polo}</p>
							<ul class="list-inside list-disc">
								{#each nomes as nome, i (i)}<li>{nome}</li>{/each}
							</ul>
						</div>
					{:else}
						<p class="text-muted-foreground">Nenhum destinatário informado.</p>
					{/each}
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header>
					<Card.Title class="text-base">Advogados</Card.Title>
				</Card.Header>
				<Card.Content class="text-sm">
					<ul class="space-y-1">
						{#each publicacao.advogados as adv, i (i)}
							<li>
								{adv.nome ?? '—'}
								{#if adv.numero_oab}
									<span class="text-muted-foreground">
										(OAB {adv.numero_oab}/{adv.uf_oab ?? '--'})
									</span>
								{/if}
							</li>
						{:else}
							<li class="text-muted-foreground">Nenhum advogado informado.</li>
						{/each}
					</ul>
					{#if publicacao.oab_origem}
						<p class="mt-3 text-muted-foreground">
							Capturada pela OAB monitorada {publicacao.oab_origem}.
						</p>
					{/if}
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header>
					<Card.Title class="text-base">Links</Card.Title>
				</Card.Header>
				<Card.Content class="space-y-2 text-sm">
					{#if publicacao.link}
						<a
							href={publicacao.link}
							target="_blank"
							rel="noopener noreferrer"
							class="flex items-center gap-1 text-primary hover:underline"
						>
							<ExternalLink class="h-4 w-4" /> Documento no tribunal
						</a>
					{/if}
					{#if publicacao.link_certidao}
						<a
							href={publicacao.link_certidao}
							target="_blank"
							rel="noopener noreferrer"
							class="flex items-center gap-1 text-primary hover:underline"
						>
							<ExternalLink class="h-4 w-4" /> Certidão do DJEN (PDF)
						</a>
					{/if}
					<p class="text-muted-foreground">
						Capturada em {formatDateTime(publicacao.capturada_em)}.
					</p>
				</Card.Content>
			</Card.Root>
		</div>
	</div>
</div>

<style>
	.publicacao-djen :global(p) {
		margin-bottom: 0.75rem;
	}
	.publicacao-djen :global(table) {
		border-collapse: collapse;
		margin-bottom: 0.75rem;
	}
	.publicacao-djen :global(td) {
		border: 1px solid var(--border);
		padding: 0.25rem 0.5rem;
		vertical-align: top;
	}
</style>
