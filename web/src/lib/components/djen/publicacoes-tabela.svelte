<script lang="ts">
	import { page } from '$app/state';
	import * as Dialog from '#lib/components/ui/dialog/index.ts';
	import Eye from '@lucide/svelte/icons/eye';
	import FileCheck2 from '@lucide/svelte/icons/file-check-2';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import ChevronUp from '@lucide/svelte/icons/chevron-up';
	import { Button } from '#lib/components/ui/button/index.ts';
	import { Badge } from '#lib/components/ui/badge/index.ts';
	import Checkbox from '#lib/components/ui/checkbox/checkbox.svelte';
	import ImportarPublicacao from './importar-publicacao.svelte';
	import { formatDateOnly } from '#lib/utils/date.ts';
	import type { AcervoItem } from '#lib/types/djen.ts';
	let {
		itens,
		selecionados,
		ocupado,
		selecionar,
		importar
	}: {
		itens: AcervoItem[];
		selecionados: number[];
		ocupado: boolean;
		selecionar: (id: number, valor: boolean) => void;
		importar: (id: number, atendido: number | null) => void;
	} = $props();
	let confirmacao = $state<AcervoItem | null>(null);
	let expandidos = $state<number[]>([]);
	const rotulos: Record<string, string> = {
		relevante: 'Relevante',
		irrelevante: 'Irrelevante',
		nao_classificado: 'Não analisado'
	};
	const situacoes: Record<string, string> = {
		nao_importada: 'Não analisado',
		pendente: 'Não analisado',
		vinculada: 'Importado',
		descartada: 'Descartado'
	};
	function detalhe(id: number) {
		expandidos = expandidos.includes(id) ? expandidos.filter((x) => x !== id) : [...expandidos, id];
	}
</script>

<div class="min-w-0 lg:overflow-x-auto lg:rounded-md lg:border">
	<table class="block w-full text-sm lg:table lg:min-w-[950px]" aria-label="Publicações">
		<thead class="hidden bg-muted/50 text-left lg:table-header-group">
			<tr>
				<th class="p-3"><span class="sr-only">Seleção</span></th><th class="p-3">
					Data / Tribunal
				</th><th class="p-3">Processo</th><th class="p-3">Partes</th><th class="p-3">
					Atendido sugerido
				</th><th class="p-3">Situação</th><th class="p-3">Ações</th>
			</tr>
		</thead>
		<tbody class="block space-y-3 lg:table-row-group lg:space-y-0">
			{#each itens as item (item.id)}
				{@const sugestoes = item.atendidos_sugeridos ?? []}
				{@const tituloParte =
					sugestoes.length === 1
						? `Parte sugerida: ${sugestoes[0].nome}`
						: sugestoes.length
							? `Revisar candidatos: ${sugestoes.map((a) => a.nome).join(' · ')}`
							: 'Escolher parte: sem sugestão'}
				<tr
					class="grid grid-cols-2 items-start gap-3 rounded-md border bg-card p-4 lg:table-row lg:border-x-0 lg:border-t-0 lg:p-0"
				>
					<td class="lg:p-3">
						<Checkbox
							aria-label={`Selecionar publicação ${item.id_djen}`}
							disabled={ocupado}
							checked={selecionados.includes(item.id_djen)}
							onCheckedChange={(v) => selecionar(item.id_djen, v === true)}
						/>
					</td>
					<td class="text-right lg:p-3 lg:text-left">
						<span class="whitespace-nowrap">{formatDateOnly(item.data_disponibilizacao)}</span><span
							class="block text-muted-foreground"
						>
							{item.sigla_tribunal}
						</span>
					</td>
					<td class="col-span-2 lg:max-w-64 lg:p-3">
						<span class="font-mono">{item.numero_processo}</span><span
							class="block truncate text-xs text-muted-foreground"
							title={item.nome_orgao}
						>
							{item.nome_orgao}
						</span>
						{#if item.id_processo}<a
								class="block text-primary underline"
								href={`/processos/${item.id_processo}`}
							>
								Processo #{item.id_processo}
							</a>{/if}
					</td>
					<td class="col-span-2 lg:max-w-64 lg:p-3">
						<span class="font-medium lg:hidden">Partes: </span><span
							class="line-clamp-2"
							title={(item.partes ?? []).join(' · ')}
						>
							{(item.partes ?? []).join(' · ') || 'Não informadas pelo DJEN'}
						</span>
					</td>
					<td class="order-5 min-w-0 lg:max-w-56 lg:p-3">
						{#if new Set((item.contextos ?? [])
								.map((c) => c.sugestao)
								.filter(Boolean)).size > 1}<Badge variant="outline">
								Sugestões divergentes
							</Badge>{/if}

						<Button
							variant="ghost"
							size="sm"
							class="max-w-full justify-start px-1 text-left lg:max-w-52"
							title={tituloParte}
							aria-label={tituloParte}
							disabled={ocupado}
							onclick={() => (confirmacao = item)}
						>
							<span class="truncate">
								{sugestoes.length ? sugestoes.map((a) => a.nome).join(' · ') : 'Sem sugestão'}
							</span>
						</Button>
					</td>
					<td class="order-4 col-span-2 lg:p-3">
						<Badge
							variant={item.situacao === 'vinculada'
								? 'default'
								: item.situacao === 'descartada'
									? 'secondary'
									: 'outline'}
						>
							{situacoes[item.situacao] ?? item.situacao}
						</Badge>
					</td>
					<td class="order-6 text-right lg:p-3">
						<div class="flex items-center justify-end gap-1">
							<Button
								variant="ghost"
								size="icon"
								class="size-8"
								title="Ler publicação"
								aria-label="Ler publicação"
								href={`/djen/acervo/${item.id}?voltar=${encodeURIComponent(page.url.pathname + page.url.search)}`}
							>
								<Eye class="size-4" />
							</Button>
							{#if item.situacao !== 'vinculada'}
								<Button
									variant="ghost"
									size="icon"
									class="size-8"
									title="Confirmar parte e importar publicação"
									aria-label="Importar publicação"
									disabled={ocupado}
									onclick={() => (confirmacao = item)}
								>
									<FileCheck2 class="size-4" />
								</Button>
							{/if}
							<Button
								variant="ghost"
								size="icon"
								class="size-8"
								disabled={ocupado}
								title={expandidos.includes(item.id) ? 'Recolher' : 'Revisar'}
								aria-label={expandidos.includes(item.id) ? 'Recolher' : 'Revisar'}
								aria-expanded={expandidos.includes(item.id)}
								aria-controls={`publicacao-detalhe-${item.id}`}
								onclick={() => detalhe(item.id)}
							>
								{#if expandidos.includes(item.id)}<ChevronUp class="size-4" />{:else}<ChevronDown
										class="size-4"
									/>{/if}
							</Button>
						</div>
					</td>
				</tr>
				{#if expandidos.includes(item.id)}
					<tr class="block lg:table-row">
						<td colspan="7" class="block rounded-md border bg-muted/30 p-4 lg:table-cell">
							<div id={`publicacao-detalhe-${item.id}`} class="space-y-3">
								<p>{item.resumo}</p>
								{#each item.contextos ?? [] as ctx}<p class="text-muted-foreground">
										{ctx.nome}: {ctx.sugestao
											? `Sugestão: ${rotulos[ctx.sugestao]} · modelo #${ctx.modelo_id}`
											: 'Sem sugestão'} · {rotulos[ctx.rotulo]}
									</p>{/each}
								{#if item.situacao !== 'vinculada'}<ImportarPublicacao
										{item}
										{ocupado}
										importar={(id) => importar(item.id_djen, id)}
									/>{/if}
								<div class="flex flex-wrap gap-4 text-primary underline">
									<a
										href={`/djen/acervo/${item.id}?voltar=${encodeURIComponent(page.url.pathname + page.url.search)}`}
									>
										Ler publicação e histórico
									</a>
									{#if item.comunicacao_id}<a href={`/djen/publicacoes/${item.comunicacao_id}`}>
											Abrir operação
										</a>{/if}
									{#if item.id_caso}<a href={`/casos/${item.id_caso}`}>Caso #{item.id_caso}</a>{/if}
								</div>
							</div>
						</td>
					</tr>
				{/if}
			{:else}<tr class="block lg:table-row">
					<td colspan="7" class="block p-8 text-center text-muted-foreground lg:table-cell">
						Nenhuma publicação neste filtro.
					</td>
				</tr>{/each}
		</tbody>
	</table>
</div>

<Dialog.Root
	open={confirmacao !== null}
	onOpenChange={(aberto) => {
		if (!aberto && !ocupado) confirmacao = null;
	}}
>
	<Dialog.Content
		showCloseButton={!ocupado}
		onInteractOutside={(e) => {
			if (ocupado) e.preventDefault();
		}}
		onEscapeKeydown={(e) => {
			if (ocupado) e.preventDefault();
		}}
	>
		<Dialog.Header>
			<Dialog.Title>Revisar parte sugerida</Dialog.Title>
			<Dialog.Description>
				Confira a parte antes de confirmar a importação desta publicação.
			</Dialog.Description>
		</Dialog.Header>
		{#if confirmacao}
			<p class="font-mono text-sm">{confirmacao.numero_processo}</p>
			<p class="text-sm">
				{(confirmacao.atendidos_sugeridos ?? []).map((a) => a.nome).join(' · ') ||
					'Nenhum atendido sugerido.'}
			</p>
			{#if confirmacao.situacao !== 'vinculada'}
				<ImportarPublicacao
					item={confirmacao}
					{ocupado}
					importar={(id) => {
						if (confirmacao) {
							importar(confirmacao.id_djen, id);
							confirmacao = null;
						}
					}}
				/>
			{:else}<p class="text-sm text-muted-foreground">Publicação já importada.</p>{/if}
		{/if}
	</Dialog.Content>
</Dialog.Root>
