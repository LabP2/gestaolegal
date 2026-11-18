<script lang="ts">
	import Contextos from './contextos.svelte';
	import FiltroTribunais from './filtro-tribunais.svelte';
	import PublicacoesTabela from './publicacoes-tabela.svelte';
	import Paginacao from '$lib/components/paginacao.svelte';
	import { onDestroy, tick } from 'svelte';
	import { goto, invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '$lib/api-client';
	import { Input } from '$lib/components/ui/input';
	import * as Select from '$lib/components/ui/select';
	import Checkbox from '$lib/components/ui/checkbox/checkbox.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import ImportarPublicacao from './importar-publicacao.svelte';
	import ImportarLote from './importar-lote.svelte';
	import { mensagemDeErro } from '$lib/utils/erros';
	import { formatDateOnly } from '$lib/utils/date';
	import { toast } from 'svelte-sonner';
	import type { AcervoPagina, RotuloExemplo } from '$lib/types/djen';
	let { dados, treino = false }: { dados: AcervoPagina; treino?: boolean } = $props();
	let selecionados = $state<number[]>([]);
	let tribunais = $state<string[]>([]);
	let filtroPolo = $state('todos');
	let filtroSituacao = $state('todos');
	let filtroFonte = $state('todos');
	let filtroSugestao = $state('todos');
	let filtroContexto = $state('todos');
	const fontes: Record<string, string> = {
		parte: 'Nome da parte',
		oab: 'OAB',
		processo: 'Número do processo'
	};
	$effect(() => {
		tribunais = page.url.searchParams
			.getAll('tribunal')
			.flatMap((t) => t.split(','))
			.filter(Boolean);
		filtroPolo = page.url.searchParams.get('polo') || 'todos';
		filtroSituacao = page.url.searchParams.get('situacao') || 'todos';
		filtroFonte = page.url.searchParams.get('fonte') || 'todos';
		filtroSugestao = page.url.searchParams.get('sugestao') || 'todos';
		filtroContexto = page.url.searchParams.get('contexto_id') || 'todos';
	});
	const contextoId = $derived(page.url.searchParams.get('contexto_id') || '');
	let contextosAvaliados = $state<number[]>([]);
	let ocupado = $state(false);
	$effect(() => {
		dados;
		selecionados = [];
		contextosAvaliados = [];
	});
	const rotulos = {
		relevante: 'Relevante',
		irrelevante: 'Irrelevante',
		nao_classificado: 'Não analisado'
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
		nao_importada: 'Não analisado',
		pendente: 'Não analisado',
		vinculada: 'Importado',
		descartada: 'Descartado'
	};
	function selecionar(id: number, valor: boolean) {
		selecionados = valor
			? [...new Set([...selecionados, id])]
			: selecionados.filter((x) => x !== id);
	}
	async function agir(
		acao: string,
		rotulo?: RotuloExemplo,
		ids = selecionados,
		atendido: number | null = null
	) {
		ocupado = true;
		try {
			const url =
				acao === 'classificar'
					? `djen/contextos/${contextoId}/classificar`
					: acao === 'importar'
						? 'djen/busca-parte/importar'
						: `djen/acervo/${acao}`;
			await api.post(url, {
				ids,
				rotulo,
				contexto_ids: contextoId ? [Number(contextoId)] : contextosAvaliados,
				id_atendido: atendido,
				...(acao === 'importar' ? { sem_parte: atendido === null } : {})
			});
			selecionados = [];
			await invalidateAll();
			toast.success('Alterações salvas.');
		} catch (err) {
			toast.error(mensagemDeErro(err, 'Não foi possível salvar.'));
		} finally {
			ocupado = false;
		}
	}
	async function limparContexto() {
		const params = new URLSearchParams(page.url.searchParams);
		params.delete('contexto_id');
		params.delete('page');
		await goto(`?${params}`);
	}
	let formulario = $state<HTMLFormElement>();
	let timer: ReturnType<typeof setTimeout>;
	onDestroy(() => clearTimeout(timer));
	async function filtrar() {
		clearTimeout(timer);
		if (ocupado || !formulario) return;
		const params = new URLSearchParams();
		for (const [chave, valor] of new FormData(formulario))
			if (String(valor).trim()) params.set(chave, String(valor).trim());
		params.set('per_page', page.url.searchParams.get('per_page') || '20');
		await goto(`?${params}`, { keepFocus: true, noScroll: true, replaceState: true });
	}
	function agendarFiltro(atraso = 500) {
		clearTimeout(timer);
		timer = setTimeout(async () => {
			await tick();
			await filtrar();
		}, atraso);
	}
	async function limparFiltros() {
		clearTimeout(timer);
		await goto(`?per_page=${dados.per_page}`, { keepFocus: true, noScroll: true });
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
	{#if treino}<Contextos contextos={dados.contextos ?? []} {treino} ocupadoExterno={ocupado} />{/if}
	{#if !treino}
		<form
			class="flex flex-wrap items-end gap-3 rounded-lg border bg-card p-6"
			method="GET"
			bind:this={formulario}
			oninput={() => agendarFiltro()}
			onsubmit={(e) => {
				e.preventDefault();
				filtrar();
			}}
		>
			<fieldset disabled={ocupado} class="contents">
				<div class="w-full sm:w-64">
					<label for="djen-nome_parte" class="mb-1 block text-sm font-medium">Nome da parte</label
					><Input
						id="djen-nome_parte"
						name="nome_parte"
						value={page.url.searchParams.get('nome_parte') ?? ''}
						placeholder="Nome completo ou parte do nome"
					/>
				</div>
				<div class="w-full sm:w-40">
					<span class="mb-1 block text-sm font-medium">Polo da parte</span>
					<input type="hidden" name="polo" value={filtroPolo === 'todos' ? '' : filtroPolo} />
					<Select.Root
						type="single"
						bind:value={filtroPolo}
						disabled={ocupado}
						onValueChange={() => agendarFiltro(0)}
					>
						<Select.Trigger class="w-full" aria-label="Polo da parte"
							>{filtroPolo === 'A'
								? 'Ativo'
								: filtroPolo === 'P'
									? 'Passivo'
									: 'Todos'}</Select.Trigger
						>
						<Select.Content
							><Select.Item value="todos">Todos</Select.Item><Select.Item value="A"
								>Ativo</Select.Item
							><Select.Item value="P">Passivo</Select.Item></Select.Content
						>
					</Select.Root>
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

				<div class="w-full sm:w-[220px]">
					<span class="mb-1 block text-sm font-medium">Situação</span>
					<input
						type="hidden"
						name="situacao"
						value={filtroSituacao === 'todos' ? '' : filtroSituacao}
					/>
					<Select.Root
						type="single"
						bind:value={filtroSituacao}
						onValueChange={() => agendarFiltro(0)}
					>
						<Select.Trigger class="w-full data-[placeholder]:text-foreground" aria-label="Situação"
							>{situacoes[filtroSituacao] ?? 'Todas'}</Select.Trigger
						>
						<Select.Content>
							<Select.Item value="todos">Todas</Select.Item>
							{#each Object.entries(situacoes).filter(([k]) => k !== 'pendente') as [valor, nome]}<Select.Item
									value={valor}>{nome}</Select.Item
								>{/each}
						</Select.Content>
					</Select.Root>
				</div>
				<div class="w-full sm:w-[200px]">
					<span class="mb-1 block text-sm font-medium">Origem da consulta</span>
					<input type="hidden" name="fonte" value={filtroFonte === 'todos' ? '' : filtroFonte} />
					<Select.Root
						type="single"
						bind:value={filtroFonte}
						onValueChange={() => agendarFiltro(0)}
					>
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
				<div class="w-full sm:w-56">
					<input type="hidden" name="tribunal" value={tribunais.join(',')} />
					<FiltroTribunais
						bind:value={tribunais}
						disabled={ocupado}
						onchange={() => agendarFiltro(0)}
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
					<Input
						id="djen-fim"
						type="date"
						name="fim"
						value={page.url.searchParams.get('fim') ?? ''}
					/>
				</div>

				<details
					class="w-full border-t pt-3"
					open={!!contextoId || !!page.url.searchParams.get('sugestao')}
				>
					<summary class="cursor-pointer text-sm text-muted-foreground">Filtros avançados</summary>
					<div class="mt-3 flex flex-wrap items-end gap-3">
						<div class="w-full sm:w-64">
							<label for="contexto-operacional" class="mb-1 block text-sm font-medium"
								>Contexto de classificação</label
							>
							<input
								type="hidden"
								name="contexto_id"
								value={filtroContexto === 'todos' ? '' : filtroContexto}
							/>
							<Select.Root
								type="single"
								bind:value={filtroContexto}
								onValueChange={() => agendarFiltro(0)}
								disabled={ocupado}
							>
								<Select.Trigger
									id="contexto-operacional"
									class="w-full"
									aria-label="Contexto de classificação"
									><span class="truncate"
										>{dados.contextos?.find((c) => String(c.id) === filtroContexto)?.nome ??
											'Todos os contextos'}</span
									></Select.Trigger
								>
								<Select.Content>
									<Select.Item value="todos">Todos os contextos</Select.Item>
									{#each dados.contextos ?? [] as ctx}<Select.Item value={String(ctx.id)}
											>{ctx.nome}</Select.Item
										>{/each}
								</Select.Content>
							</Select.Root>
						</div>
						<div class="w-full sm:w-52">
							<label for="sugestao-djen" class="mb-1 block text-sm font-medium"
								>Sugestão do modelo</label
							>
							<input
								type="hidden"
								name="sugestao"
								value={filtroSugestao === 'todos' ? '' : filtroSugestao}
							/>
							<Select.Root
								type="single"
								bind:value={filtroSugestao}
								onValueChange={() => agendarFiltro(0)}
							>
								<Select.Trigger id="sugestao-djen" class="w-full" aria-label="Sugestão do modelo"
									>{filtroSugestao === 'todos'
										? 'Todas'
										: filtroSugestao === 'sem_sugestao'
											? 'Sem sugestão'
											: rotulos[filtroSugestao as RotuloExemplo]}</Select.Trigger
								>
								<Select.Content
									><Select.Item value="todos">Todas</Select.Item><Select.Item value="relevante"
										>Relevante</Select.Item
									><Select.Item value="irrelevante">Irrelevante</Select.Item><Select.Item
										value="sem_sugestao">Sem sugestão</Select.Item
									></Select.Content
								>
							</Select.Root>
						</div>
					</div>
				</details>
				<Button type="submit" disabled={ocupado}>Filtrar</Button>
				<Button type="button" variant="ghost" disabled={ocupado} onclick={limparFiltros}
					>Limpar filtros</Button
				>
			</fieldset>
		</form>
	{/if}
	{#if !treino && contextoId}
		<div class="flex flex-wrap items-center gap-2 text-sm">
			<Badge variant="secondary" class="max-w-full gap-2 rounded-full px-3 py-1">
				<span class="break-words"
					>Contexto: {dados.contextos?.find((c) => String(c.id) === contextoId)?.nome ??
						contextoId}</span
				>
				<button
					type="button"
					class="shrink-0 rounded px-1 hover:bg-muted"
					aria-label="Limpar contexto de classificação"
					onclick={limparContexto}
					disabled={ocupado}>×</button
				>
			</Badge>
		</div>
	{/if}
	{#if treino && !contextoId}
		<p class="py-8 text-center text-muted-foreground">
			Selecione ou crie um contexto para começar.
		</p>
	{:else}
		<div
			class={`flex flex-wrap items-end gap-3 ${treino ? 'py-2' : 'rounded-lg border bg-card p-3'}`}
		>
			<span class="text-sm text-muted-foreground"
				>{selecionados.length ? `${selecionados.length} selecionadas` : 'Nenhuma selecionada'}</span
			>
			{#if treino}
				{#each Object.entries(rotulos) as [rotulo, nome]}<Button
						variant="outline"
						disabled={ocupado || !selecionados.length || !contextoId}
						onclick={() => agir('classificar', rotulo as RotuloExemplo)}>{nome}</Button
					>{/each}
			{:else}
				<ImportarLote
					itens={dados.items}
					{selecionados}
					total={dados.total}
					contextoIds={contextoId ? [Number(contextoId)] : contextosAvaliados}
					bind:ocupado
				/>
				<Button
					variant="outline"
					disabled={ocupado || !selecionados.length}
					onclick={() => agir('descartar')}>Descartar</Button
				>
				{#if !contextoId && dados.contextos?.length}
					<details class="w-full text-sm">
						<summary class="cursor-pointer text-muted-foreground"
							>Avaliar contextos ao importar ou descartar{contextosAvaliados.length
								? ` (${contextosAvaliados.length} selecionado(s))`
								: ''}</summary
						>
						<fieldset class="mt-3 space-y-2 rounded-md border p-3">
							<legend class="text-sm">Aplicar avaliação também aos contextos selecionados</legend>
							<p class="text-xs text-muted-foreground">
								Sem seleção, apenas importa ou descarta. Avaliações manuais anteriores são
								preservadas.
							</p>
							{#each dados.contextos as ctx}<label
									class="mr-4 inline-flex items-center gap-2 text-sm"
									><input
										type="checkbox"
										value={ctx.id}
										bind:group={contextosAvaliados}
									/>{ctx.nome}</label
								>{/each}
						</fieldset>
					</details>
				{/if}
			{/if}
		</div>
		<p class="text-sm text-muted-foreground">
			{dados.total} publicações encontradas.
		</p>
		<label class="flex items-center gap-2 text-sm"
			><Checkbox
				disabled={ocupado || !dados.items.length}
				checked={dados.items.length > 0 &&
					dados.items.every((i) => selecionados.includes(i.id_djen))}
				onCheckedChange={(checked) => {
					selecionados = checked === true ? dados.items.map((i) => i.id_djen) : [];
				}}
			/>Selecionar esta página</label
		>
		{#if !treino}
			<PublicacoesTabela
				itens={dados.items}
				{selecionados}
				{ocupado}
				{selecionar}
				importar={(id, atendido) => agir('importar', undefined, [id], atendido)}
			/>
		{:else}
			<ul class="space-y-3">
				{#each dados.items as item (item.id)}
					<li
						class={`flex gap-3 rounded-lg border-2 p-4 transition-colors ${estilosPublicacao[treino ? (contextoId ? item.rotulo : 'nao_classificado') : item.situacao === 'vinculada' ? 'relevante' : item.situacao === 'descartada' ? 'irrelevante' : 'nao_classificado']}`}
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
								<strong>{item.numero_processo}</strong><span
									>{formatDateOnly(item.data_disponibilizacao)}</span
								><span>{item.sigla_tribunal}</span>
							</div>
							<div class="flex flex-wrap gap-2">
								{#if treino && contextoId}
									<Badge
										variant="outline"
										class={`rounded-full px-3 py-1 ${estilosRotulo[item.rotulo]}`}
										title="Classificação de relevância"
									>
										<span aria-hidden="true" class="size-1.5 rounded-full bg-current"
										></span>{rotulos[item.rotulo]}
									</Badge>
								{/if}
								{#if !treino}
									<Badge
										variant="outline"
										class={`rounded-full px-3 py-1 ${estilosSituacao[item.situacao] ?? ''}`}
										title="Situação da importação">{situacoes[item.situacao]}</Badge
									>
								{/if}
							</div>
							{#if !treino}
								{#if new Set((item.contextos ?? [])
										.map((c) => c.sugestao)
										.filter(Boolean)).size > 1}<Badge variant="outline">Sugestões divergentes</Badge
									>{/if}
								{#each item.contextos ?? [] as ctx}<p class="text-sm">
										<strong>{ctx.nome}:</strong>
										{ctx.sugestao
											? `Sugestão: ${rotulos[ctx.sugestao]} · modelo #${ctx.modelo_id}`
											: 'Sem sugestão'}{#if ctx.rotulo !== 'nao_classificado'}
											· Avaliação registrada: {rotulos[ctx.rotulo]}{/if}
									</p>{/each}
							{/if}
							<p class="text-sm">
								<strong>Partes:</strong>
								{(item.partes ?? []).join(' · ') || 'Não informadas pelo DJEN'}
							</p>
							<p class="text-sm text-muted-foreground">{item.nome_orgao}</p>
							<p class="line-clamp-3 text-sm">{item.resumo}</p>
							{#if !treino && item.situacao !== 'vinculada'}
								<ImportarPublicacao
									{item}
									{ocupado}
									importar={(id) => agir('importar', undefined, [item.id_djen], id)}
								/>
							{/if}
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
		{/if}
		<Paginacao
			total={dados.total}
			page={dados.page}
			per_page={dados.per_page}
			disabled={ocupado}
			tamanhos={!treino}
		/>
	{/if}
</div>
