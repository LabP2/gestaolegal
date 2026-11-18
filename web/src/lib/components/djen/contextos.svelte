<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '$lib/api-client';
	import * as Select from '$lib/components/ui/select';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { toast } from 'svelte-sonner';
	import { TRIBUNAIS_DJEN } from '$lib/utils/tribunais-djen';
	import { mensagemDeErro } from '$lib/utils/erros';
	import type { ContextoDjen } from '$lib/types/djen';
	let {
		contextos,
		treino,
		ocupadoExterno = false
	}: { contextos: ContextoDjen[]; treino: boolean; ocupadoExterno?: boolean } = $props();
	let criando = $state(false);
	let contextosAtualizados = $state<ContextoDjen[] | null>(null);
	$effect(() => {
		contextos;
		contextosAtualizados = null;
	});
	let filtroRotulo = $state('nao_classificado');
	$effect(() => {
		filtroRotulo =
			page.url.searchParams.get('rotulo') ||
			(page.url.searchParams.has('rotulo') ? 'todos' : 'nao_classificado');
	});
	const rotulos = {
		nao_classificado: 'Não analisado',
		relevante: 'Relevante',
		irrelevante: 'Irrelevante'
	};
	let nome = $state(''),
		nomes = $state(''),
		tribunais = $state<string[]>([]),
		ocupado = $state(false);
	const selecionado = $derived(
		(contextosAtualizados ?? contextos).find(
			(c) => String(c.id) === page.url.searchParams.get('contexto_id')
		)
	);
	const emTreino = $derived(
		selecionado?.treino_status === 'na_fila' || selecionado?.treino_status === 'executando'
	);
	$effect(() => {
		if (!treino || !emTreino) return;
		let ativo = true;
		let consultando = false;
		const timer = setInterval(async () => {
			if (consultando) return;
			consultando = true;
			try {
				const atualizados = await api.get<ContextoDjen[]>('djen/contextos');
				if (ativo) contextosAtualizados = atualizados;
			} catch {
				// A próxima consulta tenta novamente sem apagar a seleção de publicações.
			} finally {
				consultando = false;
			}
		}, 5000);
		return () => {
			ativo = false;
			clearInterval(timer);
		};
	});
	async function selecionar(id: string) {
		const p = treino ? new URLSearchParams() : new URLSearchParams(page.url.searchParams);
		p.delete('page');
		p.delete('rotulo');
		if (id) p.set('contexto_id', id);
		else p.delete('contexto_id');
		await goto(`?${p}`);
	}
	async function criar(e: SubmitEvent) {
		e.preventDefault();
		ocupado = true;
		try {
			const c = await api.post<ContextoDjen>('djen/contextos', {
				nome,
				nomes: nomes
					.split(';')
					.map((s) => s.trim())
					.filter(Boolean),
				tribunais
			});
			nome = nomes = '';
			tribunais = [];
			criando = false;
			await selecionar(String(c.id));
			await invalidateAll();
			toast.success('Contexto criado.');
		} catch (e) {
			toast.error(mensagemDeErro(e, 'Não foi possível criar o contexto'));
		} finally {
			ocupado = false;
		}
	}
	async function treinar() {
		if (!selecionado || ocupado) return;
		ocupado = true;
		try {
			await api.post(`djen/contextos/${selecionado.id}/treinar`, {});
			await invalidateAll();
			toast.success('Treino solicitado. Você pode continuar usando a aplicação.');
		} catch (e) {
			toast.error(mensagemDeErro(e, 'Não foi possível treinar'));
		} finally {
			ocupado = false;
		}
	}
</script>

<section class="space-y-3 rounded-lg border bg-card p-4" aria-label="Contextos de classificação">
	<div class="flex flex-wrap items-end gap-3">
		<div class="min-w-0 flex-1 space-y-2">
			<label for="contexto-djen" class="block text-sm font-medium">Contexto de classificação</label>
			<Select.Root
				type="single"
				value={selecionado ? String(selecionado.id) : 'todos'}
				onValueChange={(id) => selecionar(id === 'todos' ? '' : id)}
				disabled={ocupado || ocupadoExterno}
			>
				<Select.Trigger id="contexto-djen" class="w-full" aria-label="Contexto de classificação"
					>{selecionado?.nome ??
						(treino
							? 'Selecione um contexto para classificar'
							: 'Todos os contextos')}</Select.Trigger
				>
				<Select.Content
					><Select.Item value="todos"
						>{treino ? 'Selecione um contexto para classificar' : 'Todos os contextos'}</Select.Item
					>
					{#each contextos as c}<Select.Item value={String(c.id)}>{c.nome}</Select.Item>{/each}
				</Select.Content>
			</Select.Root>
		</div>
		{#if treino}<Button
				type="button"
				variant="outline"
				aria-expanded={criando}
				onclick={() => (criando = !criando)}
				disabled={ocupado || ocupadoExterno}
				>{criando ? 'Cancelar criação' : 'Novo contexto'}</Button
			>{/if}
	</div>
	{#if treino && criando}
		<form class="mt-3 space-y-3" onsubmit={criar}>
			<label class="block text-sm"
				>Nome do contexto<Input
					bind:value={nome}
					required
					minlength={3}
					maxlength={150}
					placeholder="UFMG — TRF6"
				/></label
			>
			<label class="block text-sm"
				>Nomes da parte (separe variações por ponto e vírgula)<Input
					bind:value={nomes}
					required
					placeholder="UFMG; Universidade Federal de Minas Gerais"
				/></label
			>
			<div class="space-y-2">
				<label for="contexto-tribunais" class="block text-sm">Tribunais</label>
				<Select.Root type="multiple" bind:value={tribunais} disabled={ocupado || ocupadoExterno}>
					<Select.Trigger
						id="contexto-tribunais"
						class="w-56 max-w-full"
						aria-label="Tribunais do contexto"
						aria-describedby="contexto-tribunais-ajuda"
					>
						<span class="truncate"
							>{tribunais.length ? tribunais.join(', ') : 'Todos os tribunais'}</span
						>
					</Select.Trigger>
					<Select.Content class="max-h-80 w-56">
						{#each TRIBUNAIS_DJEN as grupo (grupo.grupo)}
							<Select.Group
								><Select.GroupHeading>{grupo.grupo}</Select.GroupHeading>
								{#each grupo.siglas as sigla (sigla)}<Select.Item value={sigla}>{sigla}</Select.Item
									>{/each}
							</Select.Group>
						{/each}
					</Select.Content>
				</Select.Root>
				<p id="contexto-tribunais-ajuda" class="text-xs text-muted-foreground">
					Sem seleção, o contexto inclui todos os tribunais.
				</p>
				{#if tribunais.length}<Button
						type="button"
						variant="ghost"
						size="sm"
						disabled={ocupado || ocupadoExterno}
						onclick={() => (tribunais = [])}>Limpar tribunais</Button
					>{/if}
			</div>
			<Button type="submit" disabled={ocupado || ocupadoExterno}>Salvar contexto</Button>
		</form>
	{/if}
	{#if selecionado}
		<p class="text-sm text-muted-foreground">
			{selecionado.nomes.join(' / ')} · {selecionado.tribunais.join(', ') || 'Todos os tribunais'}
		</p>
		{#if treino}
			<form method="GET" class="space-y-3 border-t pt-4" aria-label="Filtros do treino">
				<input type="hidden" name="contexto_id" value={selecionado.id} />
				<div class="flex flex-wrap items-end gap-3">
					<div class="w-56 max-w-full">
						<label for="treino-rotulo" class="mb-1 block text-sm font-medium">Classificação</label>
						<input
							type="hidden"
							name="rotulo"
							value={filtroRotulo === 'todos' ? '' : filtroRotulo}
						/>
						<Select.Root type="single" bind:value={filtroRotulo}>
							<Select.Trigger id="treino-rotulo" class="w-full" aria-label="Classificação"
								>{rotulos[filtroRotulo as keyof typeof rotulos] ?? 'Todas'}</Select.Trigger
							>
							<Select.Content
								><Select.Item value="todos">Todas</Select.Item
								>{#each Object.entries(rotulos) as [id, label]}<Select.Item value={id}
										>{label}</Select.Item
									>{/each}</Select.Content
							>
						</Select.Root>
					</div>
					<Button type="submit" disabled={ocupado || ocupadoExterno}>Filtrar</Button>
				</div>
				<details
					open={!!(
						page.url.searchParams.get('numero_processo') ||
						page.url.searchParams.get('inicio') ||
						page.url.searchParams.get('fim')
					)}
				>
					<summary class="cursor-pointer text-sm text-muted-foreground">Filtros adicionais</summary>
					<div class="mt-3 flex flex-wrap items-end gap-3">
						<label class="block text-sm"
							>Número do processo<Input
								name="numero_processo"
								value={page.url.searchParams.get('numero_processo') ?? ''}
								placeholder="Com ou sem máscara"
							/></label
						>
						<label class="block text-sm"
							>De<Input
								name="inicio"
								type="date"
								value={page.url.searchParams.get('inicio') ?? ''}
							/></label
						>
						<label class="block text-sm"
							>Até<Input
								name="fim"
								type="date"
								value={page.url.searchParams.get('fim') ?? ''}
							/></label
						>
					</div>
				</details>
			</form>
			<div class="space-y-3 border-t pt-4">
				<p class="text-sm">
					{selecionado.contagens.relevante ?? 0} relevantes · {selecionado.contagens.irrelevante ??
						0}
					irrelevantes · {selecionado.contagens.nao_classificado ?? 0} não analisadas
				</p>
				{#if selecionado.treino_status === 'na_fila'}<p
						role="status"
						class="text-sm text-muted-foreground"
					>
						Treino na fila. Aguardando o processamento em segundo plano.
					</p>
				{:else if selecionado.treino_status === 'executando'}<p
						role="status"
						class="text-sm text-muted-foreground"
					>
						Treinando modelo em segundo plano. Você pode sair desta tela.
					</p>
				{:else if selecionado.treino_status === 'erro'}<p
						role="alert"
						class="text-sm text-destructive"
					>
						{selecionado.treino_erro || 'O treinamento falhou. Tente novamente.'}
					</p>
				{:else if selecionado.treino_status === 'concluido'}<p
						role="status"
						class="text-sm text-muted-foreground"
					>
						Treino concluído. As sugestões são atualizadas em lotes em segundo plano.
					</p>{/if}
				<Button onclick={treinar} disabled={ocupado || emTreino || !selecionado.pode_treinar}
					>{emTreino
						? 'Treino em andamento…'
						: ocupado
							? 'Solicitando…'
							: 'Treinar modelo experimental'}</Button
				>
				<p class="text-xs text-muted-foreground">
					Mínimo: 200 rótulos, 50 de cada classe e 10 processos distintos. O modelo apenas sugere;
					não importa nem descarta.
				</p>
				{#if selecionado.modelo}<p class="text-sm">
						Modelo #{selecionado.modelo.id} · Precisão: {(
							selecionado.modelo.metricas.precisao * 100
						).toFixed(1)}% · Relevantes identificadas: {(
							selecionado.modelo.metricas.revocacao * 100
						).toFixed(1)}% · F1: {selecionado.modelo.metricas.f1.toFixed(2)}. Avaliação experimental
						por processo.
					</p>{/if}
			</div>
		{/if}
	{/if}
</section>
