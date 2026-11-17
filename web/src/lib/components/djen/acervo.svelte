<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '$lib/api-client';
	import { Input } from '$lib/components/ui/input';
	import * as Select from '$lib/components/ui/select';
	import Checkbox from '$lib/components/ui/checkbox/checkbox.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import AtendidoSelectorDialog from '$lib/components/atendido-selector-dialog.svelte';
	import { mensagemDeErro } from '$lib/utils/erros';
	import { toast } from 'svelte-sonner';
	import type { Atendido } from '$lib/types';
	import type { AcervoPagina, RotuloExemplo } from '$lib/types/djen';
	let { dados, treino = false }: { dados: AcervoPagina; treino?: boolean } = $props();
	let selecionados = $state<number[]>([]);
	let atendidosIds = $state<number[]>([]);
	let atendidos = $state<Atendido[]>([]);
	let parte = $state('');
	let filtroRotulo = $state('todos');
	let filtroSituacao = $state('todos');
	let filtroFonte = $state('todos');
	const fontes: Record<string, string> = {
		parte: 'Nome da parte',
		oab: 'OAB',
		processo: 'Número do processo'
	};
	$effect(() => {
		filtroRotulo =
			(page.url.searchParams.get('rotulo') ?? (treino ? 'nao_classificado' : '')) || 'todos';
		filtroSituacao = page.url.searchParams.get('situacao') || 'todos';
		filtroFonte = page.url.searchParams.get('fonte') || 'todos';
	});
	let ocupado = $state(false);
	$effect(() => {
		dados;
		selecionados = [];
	});
	const rotulos = {
		relevante: 'Relevante',
		irrelevante: 'Irrelevante',
		nao_classificado: 'Não classificado'
	};
	const estilosPublicacao: Record<RotuloExemplo, string> = {
		relevante: 'border-green-600 bg-card dark:border-green-500',
		nao_classificado: 'border-red-500 bg-card dark:border-red-400',
		irrelevante:
			'border-slate-200 bg-slate-100 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'
	};
	const estilosRotulo: Record<RotuloExemplo, string> = {
		relevante:
			'border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200',
		nao_classificado:
			'border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200',
		irrelevante:
			'border-slate-300 bg-slate-200 text-slate-700 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200'
	};
	const estilosSituacao: Record<string, string> = {
		nao_importada:
			'border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200',
		pendente:
			'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200',
		vinculada:
			'border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-200',
		descartada:
			'border-slate-300 bg-slate-200 text-slate-700 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200'
	};
	const situacoes: Record<string, string> = {
		nao_importada: 'Não importada',
		pendente: 'Pendente',
		vinculada: 'Importada / vinculada',
		descartada: 'Descartada'
	};
	function selecionar(id: number, valor: boolean) {
		selecionados = valor
			? [...new Set([...selecionados, id])]
			: selecionados.filter((x) => x !== id);
	}
	async function agir(acao: string, rotulo?: RotuloExemplo) {
		ocupado = true;
		try {
			const url = acao === 'importar' ? 'djen/busca-parte/importar' : `djen/acervo/${acao}`;
			await api.post(url, { ids: selecionados, rotulo, id_atendido: parte ? Number(parte) : null });
			selecionados = [];
			await invalidateAll();
			toast.success('Alterações salvas.');
		} catch (err) {
			toast.error(mensagemDeErro(err, 'Não foi possível salvar.'));
		} finally {
			ocupado = false;
		}
	}
	function paginaUrl(n: number) {
		const p = new URLSearchParams(page.url.searchParams);
		p.set('page', String(n));
		return `?${p}`;
	}
</script>

<div class="space-y-6">
	<header class="space-y-2">
		<h1 class="text-3xl font-bold">
			{treino ? 'Acervo para treino' : 'Publicações do DJEN'}
		</h1>
		<p class="text-muted-foreground">
			{treino
				? 'Classifique a relevância sem criar vínculos com processos ou casos.'
				: 'Todas as publicações capturadas ficam salvas para importar e trabalhar depois.'}
		</p>
	</header>
	<form class="flex flex-wrap items-end gap-3 rounded-lg border bg-card p-6" method="GET">
		<div class="w-full sm:w-64">
			<label for="djen-nome_parte" class="mb-1 block text-sm font-medium">Nome da parte</label
			><Input
				id="djen-nome_parte"
				name="nome_parte"
				value={page.url.searchParams.get('nome_parte') ?? ''}
				placeholder="Nome completo ou parte do nome"
			/>
		</div>
		<div class="w-full sm:w-64">
			<label for="djen-numero_processo" class="mb-1 block text-sm font-medium"
				>Número do processo</label
			><Input
				id="djen-numero_processo"
				name="numero_processo"
				value={page.url.searchParams.get('numero_processo') ?? ''}
				placeholder="Com ou sem máscara"
			/>
		</div>
		<div class="w-full sm:w-64">
			<label for="djen-oab" class="mb-1 block text-sm font-medium">OAB</label><Input
				id="djen-oab"
				name="oab"
				value={page.url.searchParams.get('oab') ?? ''}
				placeholder="Número ou número/UF"
			/>
		</div>
		<div class="w-full sm:w-[200px]">
			<span class="mb-1 block text-sm font-medium">Classificação</span>
			<input type="hidden" name="rotulo" value={filtroRotulo === 'todos' ? '' : filtroRotulo} />
			<Select.Root type="single" bind:value={filtroRotulo}>
				<Select.Trigger class="w-full data-[placeholder]:text-foreground" aria-label="Classificação"
					>{rotulos[filtroRotulo as RotuloExemplo] ?? 'Todas'}</Select.Trigger
				>
				<Select.Content>
					<Select.Item value="todos">Todas</Select.Item>
					{#each Object.entries(rotulos) as [valor, nome]}<Select.Item value={valor}
							>{nome}</Select.Item
						>{/each}
				</Select.Content>
			</Select.Root>
		</div>
		<div class="w-full sm:w-[220px]">
			<span class="mb-1 block text-sm font-medium">Situação</span>
			<input
				type="hidden"
				name="situacao"
				value={filtroSituacao === 'todos' ? '' : filtroSituacao}
			/>
			<Select.Root type="single" bind:value={filtroSituacao}>
				<Select.Trigger class="w-full data-[placeholder]:text-foreground" aria-label="Situação"
					>{situacoes[filtroSituacao] ?? 'Todas'}</Select.Trigger
				>
				<Select.Content>
					<Select.Item value="todos">Todas</Select.Item>
					{#each Object.entries(situacoes) as [valor, nome]}<Select.Item value={valor}
							>{nome}</Select.Item
						>{/each}
				</Select.Content>
			</Select.Root>
		</div>
		<div class="w-full sm:w-[200px]">
			<span class="mb-1 block text-sm font-medium">Origem da consulta</span>
			<input type="hidden" name="fonte" value={filtroFonte === 'todos' ? '' : filtroFonte} />
			<Select.Root type="single" bind:value={filtroFonte}>
				<Select.Trigger
					class="w-full data-[placeholder]:text-foreground"
					aria-label="Origem da consulta">{fontes[filtroFonte] ?? 'Todas'}</Select.Trigger
				>
				<Select.Content>
					<Select.Item value="todos">Todas</Select.Item>
					{#each Object.entries(fontes) as [valor, nome]}<Select.Item value={valor}
							>{nome}</Select.Item
						>{/each}
				</Select.Content>
			</Select.Root>
		</div>
		<div class="w-full sm:w-28">
			<label for="djen-tribunal" class="mb-1 block text-sm font-medium">Tribunal</label>
			<Input
				id="djen-tribunal"
				name="tribunal"
				value={page.url.searchParams.get('tribunal') ?? ''}
				placeholder="TJMG"
			/>
		</div>
		<div class="w-full sm:w-auto">
			<label for="djen-inicio" class="mb-1 block text-sm font-medium">De</label>
			<Input
				id="djen-inicio"
				type="date"
				name="inicio"
				value={page.url.searchParams.get('inicio') ?? ''}
			/>
		</div>
		<div class="w-full sm:w-auto">
			<label for="djen-fim" class="mb-1 block text-sm font-medium">Até</label>
			<Input id="djen-fim" type="date" name="fim" value={page.url.searchParams.get('fim') ?? ''} />
		</div>
		<Button type="submit">Filtrar</Button>
	</form>
	<div class="flex flex-wrap items-end gap-3 rounded-lg border bg-card p-6">
		<span>{selecionados.length} selecionada(s)</span>
		{#if treino}
			{#each Object.entries(rotulos) as [rotulo, nome]}<Button
					variant="outline"
					disabled={ocupado || !selecionados.length}
					onclick={() => agir('classificar', rotulo as RotuloExemplo)}>{nome}</Button
				>{/each}
		{:else}
			<AtendidoSelectorDialog
				bind:selectedAtendidosIds={atendidosIds}
				onSelect={(itens) => {
					atendidos = itens;
					parte = itens[0] ? String(itens[0].id) : '';
				}}
			/>
			<div class="w-full sm:w-64">
				<span class="mb-1 block text-sm font-medium">Parte para processos novos</span>
				<Select.Root type="single" bind:value={parte}>
					<Select.Trigger class="w-full" aria-label="Parte para processos novos"
						><span class="truncate"
							>{atendidos.find((a) => String(a.id) === parte)?.nome ??
								'Selecione se necessário'}</span
						></Select.Trigger
					>
					<Select.Content>
						{#each atendidos as a}<Select.Item value={String(a.id)}>{a.nome}</Select.Item>{/each}
					</Select.Content>
				</Select.Root>
			</div>
			<Button disabled={ocupado || !selecionados.length} onclick={() => agir('importar')}
				>Importar selecionadas</Button
			>
			<Button
				variant="outline"
				disabled={ocupado || !selecionados.length}
				onclick={() => agir('descartar')}>Descartar e marcar irrelevante</Button
			>
		{/if}
	</div>
	<p class="text-sm text-muted-foreground">
		{dados.total} publicação(ões). Não selecionar mantém o estado atual.
	</p>
	<label class="flex items-center gap-2 text-sm"
		><Checkbox
			disabled={ocupado || !dados.items.length}
			checked={dados.items.length > 0 && dados.items.every((i) => selecionados.includes(i.id_djen))}
			onCheckedChange={(checked) => {
				selecionados = checked === true ? dados.items.map((i) => i.id_djen) : [];
			}}
		/>Selecionar esta página</label
	>
	<ul class="space-y-3">
		{#each dados.items as item (item.id)}
			<li
				class={`flex gap-3 rounded-lg border-2 p-4 transition-colors ${estilosPublicacao[item.rotulo]}`}
			>
				<Checkbox
					class="mt-1"
					aria-label={`Selecionar publicação ${item.id_djen}`}
					disabled={ocupado}
					checked={selecionados.includes(item.id_djen)}
					onCheckedChange={(checked) => selecionar(item.id_djen, checked === true)}
				/>
				<div class="min-w-0 flex-1 space-y-2">
					<div class="flex flex-wrap gap-3 text-sm">
						<strong>{item.numero_processo}</strong><span>{item.data_disponibilizacao}</span><span
							>{item.sigla_tribunal}</span
						>
					</div>
					<div class="flex flex-wrap gap-2">
						<Badge
							variant="outline"
							class={`rounded-full px-3 py-1 ${estilosRotulo[item.rotulo]}`}
							title="Classificação de relevância"
						>
							<span aria-hidden="true" class="size-1.5 rounded-full bg-current"></span>{rotulos[
								item.rotulo
							]}
						</Badge>
						<Badge
							variant="outline"
							class={`rounded-full px-3 py-1 ${estilosSituacao[item.situacao] ?? ''}`}
							title="Situação da importação">{situacoes[item.situacao]}</Badge
						>
					</div>
					<p class="text-sm text-muted-foreground">{item.nome_orgao}</p>
					<p class="line-clamp-3 text-sm">{item.resumo}</p>
					<div
						class={`flex flex-wrap gap-4 text-sm ${item.rotulo === 'irrelevante' ? 'text-slate-600 dark:text-slate-300' : 'text-primary'}`}
					>
						<a
							class="underline"
							href={`/djen/acervo/${item.id}?voltar=${encodeURIComponent(page.url.pathname + page.url.search)}`}
							>Ler publicação e histórico</a
						>{#if item.comunicacao_id}<a
								class="underline"
								href={`/djen/publicacoes/${item.comunicacao_id}`}>Abrir operação</a
							>{/if}{#if item.id_processo}<a
								class="underline"
								href={`/processos/${item.id_processo}`}>Processo #{item.id_processo}</a
							>{/if}{#if item.id_caso}<a class="underline" href={`/casos/${item.id_caso}`}
								>Caso #{item.id_caso}</a
							>{/if}
					</div>
				</div>
			</li>
		{:else}<li class="p-6">Nenhuma publicação neste filtro.</li>{/each}
	</ul>
	<nav class="flex gap-4 text-sm" aria-label="Paginação">
		{#if dados.page > 1}<a class="underline" href={paginaUrl(dados.page - 1)}>Anterior</a>{/if}<span
			>Página {dados.page}</span
		>{#if dados.page * dados.per_page < dados.total}<a
				class="underline"
				href={paginaUrl(dados.page + 1)}>Próxima</a
			>{/if}
	</nav>
</div>
