<script lang="ts">
	import { goto, refreshAll } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api-client.ts';
	import * as Select from '#lib/components/ui/select/index.ts';
	import { Button } from '#lib/components/ui/button/index.ts';
	import { toast } from 'svelte-sonner';
	import { mensagemDeErro } from '#lib/utils/erros.ts';
	import type { ContextoDjen } from '#lib/types/djen.ts';
	import ContextoEditor from './contexto-editor.svelte';
	import TreinoPainel from './treino-painel.svelte';
	let {
		contextos,
		treino,
		ocupadoExterno = false
	}: { contextos: ContextoDjen[]; treino: boolean; ocupadoExterno?: boolean } = $props();
	let editor = $state<'novo' | 'editar' | null>(null);
	let atualizado = $state<ContextoDjen[] | null>(null);
	let ocupado = $state(false);
	$effect(() => {
		contextos;
		atualizado = null;
	});
	const selecionado = $derived(
		(atualizado ?? contextos).find((c) => String(c.id) === page.url.searchParams.get('contexto_id'))
	);
	const emTreino = $derived(
		selecionado?.treino_status === 'na_fila' || selecionado?.treino_status === 'executando'
	);
	$effect(() => {
		if (!treino || !emTreino) return;
		const controller = new AbortController();
		let consultando = false;
		const timer = setInterval(async () => {
			if (consultando) return;
			consultando = true;
			try {
				const lista = await api.get<ContextoDjen[]>('djen/contextos', {
					signal: controller.signal
				});
				if (!controller.signal.aborted) atualizado = lista;
			} catch {
				/* O próximo ciclo tenta novamente. */
			} finally {
				consultando = false;
			}
		}, 3000);
		return () => {
			controller.abort();
			clearInterval(timer);
		};
	});
	async function selecionar(id: string) {
		editor = null;
		const p = new URLSearchParams(page.url.search);
		p.delete('page');
		p.delete('rotulo');
		if (id) p.set('contexto_id', id);
		else p.delete('contexto_id');
		await goto(`?${p}`);
	}
	async function salvo(ctx: ContextoDjen) {
		editor = null;
		await selecionar(String(ctx.id));
		await refreshAll();
		toast.success('Contexto salvo.');
	}
	async function treinar() {
		if (!selecionado || ocupado) return;
		ocupado = true;
		try {
			await api.post(`djen/contextos/${selecionado.id}/treinar`, {});
			await refreshAll();
			toast.success('Treino solicitado. Você pode continuar usando a aplicação.');
		} catch (e) {
			toast.error(mensagemDeErro(e, 'Não foi possível treinar'));
		} finally {
			ocupado = false;
		}
	}
</script>

<section class="space-y-4 rounded-lg border bg-card p-4" aria-label="Contextos de classificação">
	<div class="flex flex-wrap items-end gap-3">
		<div class="w-full min-w-0 space-y-2 sm:w-auto sm:min-w-64 sm:flex-1">
			<label for="contexto-djen" class="block text-sm font-medium">Contexto de classificação</label>
			<Select.Root
				type="single"
				value={selecionado ? String(selecionado.id) : 'todos'}
				onValueChange={(id) => selecionar(id === 'todos' ? '' : id)}
				disabled={ocupado || ocupadoExterno}
			>
				<Select.Trigger id="contexto-djen" class="w-full" aria-label="Contexto de classificação">
					{selecionado?.nome ?? 'Todo o acervo'}
				</Select.Trigger>
				<Select.Content>
					<Select.Item value="todos">Todo o acervo</Select.Item>{#each contextos as c}<Select.Item
							value={String(c.id)}
						>
							{c.nome}
						</Select.Item>{/each}
				</Select.Content>
			</Select.Root>
		</div>
		{#if treino}<Button
				variant="outline"
				disabled={ocupado || ocupadoExterno}
				onclick={() => (editor = editor === 'novo' ? null : 'novo')}
			>
				{editor === 'novo' ? 'Cancelar criação' : 'Novo contexto'}
			</Button>{/if}
		{#if treino && selecionado}<Button
				variant="outline"
				disabled={ocupado || ocupadoExterno || emTreino}
				onclick={() => (editor = editor === 'editar' ? null : 'editar')}
			>
				{editor === 'editar' ? 'Cancelar edição' : 'Editar contexto'}
			</Button>{/if}
	</div>
	{#if editor}{#key `${editor}-${selecionado?.id ?? 0}`}<ContextoEditor
				contexto={editor === 'editar' ? selecionado : null}
				salvar={salvo}
			/>{/key}{/if}
	{#if selecionado}
		<p class="text-sm">{selecionado.descricao || 'Objetivo não informado.'}</p>
		<p class="text-sm text-muted-foreground">
			{Object.entries(
				selecionado.criterios ?? { nomes: selecionado.nomes, tribunal: selecionado.tribunais }
			)
				.filter(([, valor]) => valor && String(valor))
				.map(([chave, valor]) => `${chave}: ${Array.isArray(valor) ? valor.join(', ') : valor}`)
				.join(' · ') || 'Todas as publicações acessíveis nesta unidade.'}
		</p>
		<p class="text-sm">
			{selecionado.contagens.relevante ?? 0} relevantes · {selecionado.contagens.irrelevante ?? 0} irrelevantes
			· {selecionado.contagens.nao_classificado ?? 0} não analisadas
		</p>
		{#if treino}
			{#if selecionado.treino_status === 'na_fila'}<p role="status" class="text-sm">
					Treino na fila. Aguardando o processamento em segundo plano.
				</p>
			{:else if selecionado.treino_status === 'executando'}<p role="status" class="text-sm">
					Treinando modelo em segundo plano. Você pode sair desta tela.
				</p>
			{:else if selecionado.treino_status === 'erro'}<p
					role="alert"
					class="text-sm text-destructive"
				>
					{selecionado.treino_erro || 'O treinamento falhou. Tente novamente.'}
				</p>
			{:else if selecionado.treino_status === 'concluido'}<p role="status" class="text-sm">
					Treino concluído. As sugestões são atualizadas em lotes em segundo plano.
				</p>{/if}
			<Button
				onclick={treinar}
				disabled={ocupado || ocupadoExterno || emTreino || !selecionado.pode_treinar}
			>
				{emTreino
					? 'Treino em andamento…'
					: selecionado.modelo
						? 'Treinar novamente'
						: 'Treinar modelo experimental'}
			</Button>
			<p class="text-xs text-muted-foreground">
				Mínimo: 200 exemplos utilizáveis, 50 de cada classe e 10 processos distintos. O modelo
				apenas sugere; não importa nem descarta.
			</p>
			{#key selecionado.id}<TreinoPainel contexto={selecionado} />{/key}
		{/if}
	{/if}
</section>
