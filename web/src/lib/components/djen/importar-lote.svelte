<script lang="ts">
	import { beforeNavigate, invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '$lib/api-client';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { mensagemDeErro } from '$lib/utils/erros';
	import type { AcervoItem, AcervoPagina } from '$lib/types/djen';
	import { toast } from 'svelte-sonner';

	let {
		itens,
		selecionados,
		total,
		contextoIds,
		ocupado = $bindable(false)
	}: {
		itens: AcervoItem[];
		selecionados: number[];
		total: number;
		contextoIds: number[];
		ocupado?: boolean;
	} = $props();
	type Grupo = { id: number; nome: string; ids: number[] };
	let aberto = $state(false);
	let grupos = $state<Grupo[]>([]);
	let ignoradas = $state(0);
	let processadas = $state(0);
	let quantidade = $state(0);
	let progresso = $state('');
	let erro = $state('');
	let contextos: number[] = [];
	let origem = '';
	let preparando = $state(false);
	let importando = $state(false);
	const pendentes = $derived(grupos.reduce((n, grupo) => n + grupo.ids.length, 0));
	beforeNavigate(({ cancel }) => {
		if (preparando || importando) {
			cancel();
			toast.info('Aguarde a conclusão do lote antes de sair.');
		}
	});

	async function preparar(todas: boolean) {
		aberto = true;
		ocupado = preparando = true;
		grupos = [];
		erro = '';
		processadas = quantidade = ignoradas = 0;
		progresso = 'Preparando lote…';
		contextos = [...contextoIds];
		origem = page.url.href;
		try {
			let lista = itens.filter((item) => selecionados.includes(item.id_djen));
			if (todas) {
				lista = [];
				const params = new URLSearchParams(page.url.searchParams);
				params.set('per_page', '100');
				for (let pagina = 1; ; pagina++) {
					params.set('page', String(pagina));
					const dados = await api.get<AcervoPagina>(`djen/acervo?${params}`);
					lista.push(...dados.items);
					progresso = `Conferindo ${lista.length} de ${dados.total} publicações…`;
					if (pagina * dados.per_page >= dados.total || !dados.items.length) break;
				}
			}
			lista = [...new Map(lista.map((item) => [item.id_djen, item])).values()];
			// Um processo novo não pode receber partes diferentes pela ordem dos lotes.
			const porProcesso = new Map<string, Set<number>>();
			for (const item of lista) {
				if (item.situacao === 'vinculada') continue;
				const ids = porProcesso.get(item.numero_processo) ?? new Set<number>();
				for (const parte of item.atendidos_sugeridos ?? []) ids.add(parte.id);
				porProcesso.set(item.numero_processo, ids);
			}
			const porParte = new Map<number, Grupo>();
			for (const item of lista) {
				const candidatos = item.atendidos_sugeridos ?? [];
				if (
					item.situacao === 'vinculada' ||
					candidatos.length !== 1 ||
					(porProcesso.get(item.numero_processo)?.size ?? 0) > 1
				) {
					ignoradas++;
					continue;
				}
				const parte = candidatos[0];
				const grupo = porParte.get(parte.id) ?? { ...parte, ids: [] };
				grupo.ids.push(item.id_djen);
				porParte.set(parte.id, grupo);
			}
			grupos = [...porParte.values()];
			quantidade = grupos.reduce((n, grupo) => n + grupo.ids.length, 0);
		} catch (e) {
			erro = mensagemDeErro(
				e,
				'Não foi possível preparar a importação. Nenhuma publicação foi importada.'
			);
		} finally {
			ocupado = preparando = false;
		}
	}

	async function confirmar() {
		if (page.url.href !== origem) {
			erro = 'Os filtros mudaram. Feche e prepare o lote novamente.';
			return;
		}
		ocupado = importando = true;
		erro = '';
		try {
			for (const grupo of grupos) {
				while (grupo.ids.length) {
					const ids = grupo.ids.slice(0, 100);
					progresso = `Importando para ${grupo.nome}: ${processadas} de ${quantidade} concluídas…`;
					await api.post('djen/busca-parte/importar', {
						ids,
						id_atendido: grupo.id,
						sem_parte: false,
						contexto_ids: contextos
					});
					grupo.ids = grupo.ids.slice(ids.length);
					processadas += ids.length;
				}
			}
			toast.success(`${processadas} publicações importadas com as partes confirmadas.`);
		} catch (e) {
			erro = mensagemDeErro(e, 'A importação foi interrompida.');
		} finally {
			try {
				await invalidateAll();
			} catch {
				toast.error('Não foi possível atualizar a lista. Os lotes concluídos estão salvos.');
			} finally {
				ocupado = importando = false;
			}
		}
	}
</script>

<svelte:window
	onbeforeunload={(evento) => {
		if (preparando || importando) {
			evento.preventDefault();
			evento.returnValue = '';
		}
	}}
/>

<Button
	class="h-auto max-w-full py-2 whitespace-normal"
	disabled={ocupado || !selecionados.length}
	onclick={() => preparar(false)}
>
	Importar selecionadas com partes sugeridas
</Button>
<Button
	class="h-auto max-w-full py-2 whitespace-normal"
	variant="outline"
	disabled={ocupado || !total}
	onclick={() => preparar(true)}
>
	Importar todas do filtro com partes sugeridas
</Button>
<Dialog.Root
	open={aberto}
	onOpenChange={(valor) => {
		if (!preparando && !importando) aberto = valor;
	}}
>
	<Dialog.Content
		class="max-h-[calc(100dvh-2rem)] overflow-y-auto break-words"
		showCloseButton={!preparando && !importando}
		onInteractOutside={(e) => {
			if (preparando || importando) e.preventDefault();
		}}
		onEscapeKeydown={(e) => {
			if (preparando || importando) e.preventDefault();
		}}
	>
		<Dialog.Header>
			<Dialog.Title>Confirmar partes e importar em lote</Dialog.Title>
			<Dialog.Description>
				Revise os atendidos sugeridos. Processos novos serão criados sem caso com a parte
				confirmada. Processos existentes mantêm suas partes e recebem as publicações.
			</Dialog.Description>
		</Dialog.Header>
		{#if preparando || importando}<p role="status" aria-live="polite">
				{progresso || 'Preparando lote…'}
			</p>{/if}
		{#if !preparando}
			<p>{quantidade} publicações aptas para importar.</p>
			<ul class="max-h-60 space-y-2 overflow-auto text-sm">
				{#each grupos as grupo}<li>
						<strong>{grupo.nome} · #{grupo.id}</strong>: {grupo.ids.length} pendentes
					</li>{/each}
			</ul>
			<p class="text-sm text-muted-foreground">
				{ignoradas} fora do lote: já importadas, sem sugestão única ou com partes divergentes no mesmo
				processo. Revise essas publicações individualmente.
			</p>
			{#if processadas}<p role="status">
					{processadas} de {quantidade} importadas. Os lotes concluídos estão salvos.
				</p>{/if}
		{/if}
		{#if erro}<p role="alert" class="text-destructive">{erro}</p>{/if}
		<Dialog.Footer>
			<Button variant="outline" disabled={preparando || importando} onclick={() => (aberto = false)}
				>Fechar</Button
			>
			<Button disabled={preparando || importando || !pendentes} onclick={confirmar}>
				{processadas ? 'Continuar importação' : 'Confirmar partes e importar'}
			</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
