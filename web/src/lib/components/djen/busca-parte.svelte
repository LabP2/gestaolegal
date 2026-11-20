<script lang="ts">
	import ProgressoBusca from '#lib/components/djen/progresso-busca.svelte';
	import { Button } from '#lib/components/ui/button/index.ts';
	import { Badge } from '#lib/components/ui/badge/index.ts';
	import { Input } from '#lib/components/ui/input/index.ts';
	import * as Card from '#lib/components/ui/card/index.ts';
	import * as Select from '#lib/components/ui/select/index.ts';
	import Checkbox from '#lib/components/ui/checkbox/checkbox.svelte';
	import AtendidoSelectorDialog from '#lib/components/atendido-selector-dialog.svelte';
	import FiltrosBusca from '#lib/components/djen/filtros-busca.svelte';
	import { unidadeAtiva } from '#lib/stores/unidade.ts';
	import { api } from '#lib/api-client.ts';
	import { mensagemDeErro } from '#lib/utils/erros.ts';
	import { formatDateOnly } from '#lib/utils/date.ts';
	import { MAX_TRIBUNAIS } from '#lib/utils/tribunais-djen.ts';
	import { toast } from 'svelte-sonner';
	import {
		BUSCA_PARTE_MAX_DIAS,
		DJEN_PAPEIS_GESTAO,
		type Atendido,
		type AtendidoNome,
		type ImportacaoBuscaParte,
		type ResultadoBuscaParte
	} from '#lib/types/index.ts';
	import X from '@lucide/svelte/icons/x';
	import Search from '@lucide/svelte/icons/search';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import type { Me } from '#lib/types/index.ts';
	import { refreshAll } from '$app/navigation';

	let {
		data,
		monitoramento = false,
		onFiltros,
		buscarTodos,
		semItensAtivos = true,
		ocupadoExterno = false,
		onOcupado
	}: {
		data: { me: Me };
		monitoramento?: boolean;
		buscarTodos?: () => Promise<void>;
		semItensAtivos?: boolean;
		ocupadoExterno?: boolean;
		onOcupado?: (valor: boolean) => void;
		onFiltros?: (filtros: { de: string; ate: string; tribunais: string[] }) => void;
	} = $props();
	const me = $derived(data.me);
	const djenAtivo = $derived(me.tenant?.djen_ativo === true);
	const pode = $derived(DJEN_PAPEIS_GESTAO.includes(me.urole));

	const MAX_NOMES = 5;

	function isoLocal(d: Date): string {
		const m = String(d.getMonth() + 1).padStart(2, '0');
		const dia = String(d.getDate()).padStart(2, '0');
		return `${d.getFullYear()}-${m}-${dia}`;
	}

	const hoje = new Date();
	const semanaPassada = new Date(hoje);
	semanaPassada.setDate(hoje.getDate() - 6);

	let nomes = $state<string[]>([]);
	let novoNome = $state('');
	let de = $state(isoLocal(semanaPassada));
	let ate = $state(isoLocal(hoje));
	let tribunais = $state<string[]>([]);
	$effect(() => {
		onFiltros?.({ de, ate, tribunais });
	});
	let cadastrando = $state(false);
	let tentouMonitorar = $state(false);
	async function monitorarNomes() {
		if (cadastrando || buscando || ocupadoExterno) return;
		tentouMonitorar = true;
		if (novoNome.trim()) {
			incluirNome(novoNome);
			novoNome = '';
		}
		if (!nomes.length) {
			toast.error('Informe pelo menos um nome para monitorar.');
			return;
		}
		if (!tribunais.length) {
			toast.error(
				'Selecione ao menos um tribunal para monitorar este nome. Todos vale apenas para a busca manual.'
			);
			return;
		}
		cadastrando = true;
		try {
			for (const nome of nomes)
				await api.post('djen/monitoramentos', { tipo: 'parte', valor: nome, tribunais });
			toast.success('Nomes adicionados ao monitoramento');
			await refreshAll();
		} catch (e) {
			toast.error(mensagemDeErro(e, 'Não foi possível adicionar todos os nomes'));
		} finally {
			cadastrando = false;
		}
	}

	// Atendidos escolhidos: fornecem nomes e a parte dos processos criados.
	let atendidosIds = $state<number[]>([]);
	let atendidos = $state<Atendido[]>([]);
	let parteId = $state('');

	let buscando = $state(false);
	$effect(() => {
		onOcupado?.(buscando || cadastrando);
	});
	let importando = $state(false);
	let marcandoNaoPertinentes = $state(false);
	const ocupado = $derived(importando || marcandoNaoPertinentes);
	let resultado = $state<ResultadoBuscaParte | null>(null);
	$effect(() => {
		$unidadeAtiva;
		resultado = null;
		marcados = [];
		atendidosIds = [];
		atendidos = [];
		parteId = '';
	});
	let marcados = $state<number[]>([]);

	function incluirNome(nome: string) {
		const limpo = nome.replace(/\s+/g, ' ').trim();
		if (!limpo) return;
		if (nomes.some((n) => n.toLocaleLowerCase('pt-BR') === limpo.toLocaleLowerCase('pt-BR'))) {
			return;
		}
		if (nomes.length >= MAX_NOMES) {
			toast.error(`No máximo ${MAX_NOMES} nomes por busca`);
			return;
		}
		nomes = [...nomes, limpo];
	}

	async function escolherAtendidos(escolhidos: Atendido[]) {
		atendidos = escolhidos;
		if (!escolhidos.some((a) => String(a.id) === parteId)) {
			parteId = escolhidos[0] ? String(escolhidos[0].id) : '';
		}
		for (const a of escolhidos) {
			incluirNome(a.nome);
			try {
				const variacoes = await api.get<AtendidoNome[]>(`atendido/${a.id}/nomes`);
				variacoes.forEach((v) => incluirNome(v.nome));
			} catch (err) {
				toast.error(mensagemDeErro(err, `Não foi possível ler as variações de ${a.nome}.`));
			}
		}
	}

	function parametros(): URLSearchParams {
		const p = new URLSearchParams();
		nomes.forEach((n) => p.append('nome', n));
		p.set('de', de);
		p.set('ate', ate);
		tribunais.forEach((t) => p.append('tribunal', t));
		return p;
	}

	async function buscar(event?: SubmitEvent) {
		event?.preventDefault();
		if (buscando || ocupadoExterno) return;
		if (novoNome.trim()) {
			incluirNome(novoNome);
			novoNome = '';
		}
		if (nomes.length === 0) {
			toast.error('Informe pelo menos um nome');
			return;
		}
		if (tribunais.length > MAX_TRIBUNAIS) {
			toast.error(`No máximo ${MAX_TRIBUNAIS} tribunais por busca`);
			return;
		}
		buscando = true;
		const unidadeConsultada = $unidadeAtiva;
		try {
			const resposta = await api.get<ResultadoBuscaParte>(`djen/busca-parte?${parametros()}`);
			if ($unidadeAtiva !== unidadeConsultada) return;
			resultado = resposta;
			marcados = [];
			pagina = 1;
		} catch (err) {
			toast.error(mensagemDeErro(err, 'Não foi possível consultar o DJEN.'));
		} finally {
			buscando = false;
		}
	}

	const importaveis = $derived(resultado?.items.filter((i) => !i.ja_no_banco) ?? []);
	const precisaParte = $derived(
		(resultado?.items ?? []).some((i) => marcados.includes(i.id_djen) && i.processo_id === null)
	);

	function alternar(id: number, marcado: boolean) {
		marcados = marcado ? [...marcados, id] : marcados.filter((m) => m !== id);
	}

	function alternarTodos(marcado: boolean) {
		marcados = marcado ? importaveis.map((i) => i.id_djen) : [];
	}

	// Paginação só na tela: a busca já trouxe tudo. A seleção vale entre páginas.
	const POR_PAGINA = 20;
	let pagina = $state(1);
	const totalPaginas = $derived(
		Math.max(1, Math.ceil((resultado?.items.length ?? 0) / POR_PAGINA))
	);
	const itensDaPagina = $derived(
		(resultado?.items ?? []).slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA)
	);
	const importaveisDaPagina = $derived(itensDaPagina.filter((i) => !i.ja_no_banco));
	const paginaToda = $derived(
		importaveisDaPagina.length > 0 && importaveisDaPagina.every((i) => marcados.includes(i.id_djen))
	);

	function alternarPagina(marcado: boolean) {
		const ids = importaveisDaPagina.map((i) => i.id_djen);
		marcados = marcado
			? [...marcados, ...ids.filter((id) => !marcados.includes(id))]
			: marcados.filter((m) => !ids.includes(m));
	}

	// O servidor aceita até 100 publicações por importação.
	const LOTE_IMPORTACAO = 100;

	function corpoDoLote(ids: number[]) {
		return {
			nome: resultado!.nomes,
			de: resultado!.de,
			ate: resultado!.ate,
			tribunal: resultado!.tribunais,
			ids,
			contexto_ids: []
		};
	}

	// Mesma seleção e mesmos lotes da importação; não cria publicação nem processo.
	async function marcarNaoPertinentes() {
		if (!resultado || marcados.length === 0) return;
		marcandoNaoPertinentes = true;
		let marcadas = 0;
		const naoEncontradas: number[] = [];
		try {
			for (let i = 0; i < marcados.length; i += LOTE_IMPORTACAO) {
				const lote = await api.post<{ descartadas: number }>(
					'djen/acervo/descartar',
					corpoDoLote(marcados.slice(i, i + LOTE_IMPORTACAO))
				);
				marcadas += lote.descartadas;
			}
			const partes = [`${marcadas} descartada(s)`];
			if (naoEncontradas.length) {
				partes.push(`${naoEncontradas.length} não encontrada(s) no DJEN`);
			}
			toast.success(partes.join(', '));
			await buscar();
		} catch (err) {
			if (marcadas) {
				toast.error(`Marcação interrompida depois de ${marcadas} publicação(ões).`);
				await buscar();
			}
			toast.error(mensagemDeErro(err, 'Não foi possível marcar as publicações.'));
		} finally {
			marcandoNaoPertinentes = false;
		}
	}

	async function importar() {
		if (!resultado || marcados.length === 0) return;
		if (precisaParte && !parteId) {
			toast.error('Escolha a parte dos processos que ainda não existem');
			return;
		}
		importando = true;
		const r: ImportacaoBuscaParte = {
			novas: 0,
			atualizadas: 0,
			vinculadas: 0,
			processos_criados: [],
			nao_encontradas: []
		};
		try {
			for (let i = 0; i < marcados.length; i += LOTE_IMPORTACAO) {
				const lote = await api.post<ImportacaoBuscaParte>('djen/busca-parte/importar', {
					...corpoDoLote(marcados.slice(i, i + LOTE_IMPORTACAO)),
					id_atendido: parteId ? Number(parteId) : null
				});
				r.novas += lote.novas;
				r.atualizadas += lote.atualizadas;
				r.vinculadas += lote.vinculadas;
				r.processos_criados.push(...lote.processos_criados);
				r.nao_encontradas.push(...lote.nao_encontradas);
			}
			const partes = [
				`${r.novas} nova(s)`,
				`${r.atualizadas} atualizada(s)`,
				`${r.vinculadas} vinculada(s)`,
				`${r.processos_criados.length} processo(s) criado(s)`
			];
			if (r.nao_encontradas.length) {
				partes.push(`${r.nao_encontradas.length} não encontrada(s) no DJEN`);
			}
			toast.success(`Importação concluída: ${partes.join(', ')}`);
			await buscar();
		} catch (err) {
			if (r.novas || r.vinculadas) {
				toast.error(
					`Importação interrompida depois de ${r.novas} nova(s) e ${r.vinculadas} vinculada(s).`
				);
				await buscar();
			}
			toast.error(mensagemDeErro(err, 'Não foi possível importar as publicações.'));
		} finally {
			importando = false;
		}
	}
</script>

{#if buscando}
	<ProgressoBusca
		detalhe="Consultando os nomes e tribunais selecionados e salvando as publicações."
	/>
{/if}

<div class="space-y-6">
	<div>
		{#if !monitoramento}<h1 class="text-3xl font-bold tracking-tight">
				Busca por parte no DJEN
			</h1>{/if}
		<p class="text-muted-foreground">
			Todas as publicações recebidas são salvas no acervo, mesmo sem importação ou classificação.
		</p>
	</div>

	{#if !djenAtivo}
		<p class="rounded-lg border bg-card p-6 text-muted-foreground">
			O DJEN não está ligado para este NPJ.
		</p>
	{:else if !pode}
		<p class="rounded-lg border bg-card p-6 text-muted-foreground">
			A busca por parte é restrita à coordenação e aos orientadores.
		</p>
	{:else}
		<form class="space-y-4 rounded-lg border bg-card p-6" onsubmit={buscar}>
			<div class="flex flex-wrap items-end gap-3">
				<div class="w-full min-w-0 flex-1 sm:min-w-72">
					<label for="busca-nome" class="mb-1 block text-sm font-medium">Nome da parte</label>
					<div class="flex gap-2">
						<Input
							id="busca-nome"
							bind:value={novoNome}
							placeholder="Nome completo ou variação (mín. 3 letras)"
							onkeydown={(e) => {
								if (e.key === 'Enter' && novoNome.trim()) {
									e.preventDefault();
									incluirNome(novoNome);
									novoNome = '';
								}
							}}
						/>
						<Button
							type="button"
							variant="outline"
							disabled={!novoNome.trim()}
							onclick={() => {
								incluirNome(novoNome);
								novoNome = '';
							}}
						>
							Adicionar
						</Button>
					</div>
				</div>
				<div>
					<span class="mb-1 block text-sm font-medium">Ou a partir de atendidos</span>
					<AtendidoSelectorDialog
						bind:selectedAtendidosIds={atendidosIds}
						onSelect={escolherAtendidos}
					/>
				</div>
			</div>

			{#if nomes.length}
				<div class="flex flex-wrap gap-2">
					{#each nomes as nome (nome)}
						<Badge variant="secondary" class="gap-1">
							{nome}
							<button
								type="button"
								class="ml-1 rounded-sm hover:text-destructive"
								title="Remover nome"
								onclick={() => (nomes = nomes.filter((n) => n !== nome))}
							>
								<X class="h-3 w-3" />
							</button>
						</Badge>
					{/each}
				</div>
			{/if}

			<div class="flex flex-wrap items-end gap-3">
				<FiltrosBusca
					bind:de
					bind:ate
					bind:tribunais
					unidades={me.unidades}
					id="busca-periodo"
					exigirTribunalMonitoramento={monitoramento}
					erroTribunais={monitoramento && tentouMonitorar && !tribunais.length}
				/>
				{#if monitoramento}<Button
						type="button"
						variant="outline"
						disabled={ocupadoExterno || cadastrando || buscando}
						onclick={monitorarNomes}
					>
						Adicionar nomes ao monitoramento
					</Button>{/if}
				<Button type="submit" disabled={buscando || ocupadoExterno}>
					<Search class="mr-2 h-4 w-4" />
					{buscando ? 'Consultando…' : monitoramento ? 'Buscar agora' : 'Buscar no DJEN'}
				</Button>
				{#if monitoramento && buscarTodos}
					<Button
						type="button"
						variant="outline"
						disabled={buscando || cadastrando || ocupadoExterno || semItensAtivos}
						onclick={buscarTodos}
					>
						Buscar todos
					</Button>
				{/if}
			</div>
			<p class="text-xs text-muted-foreground">
				Período de até {BUSCA_PARTE_MAX_DIAS} dias, até {MAX_NOMES} nomes e até {MAX_TRIBUNAIS}
				tribunais por busca. Na busca manual, sem tribunal marcado, busca em todos.
			</p>
		</form>

		{#if resultado}
			<Card.Root>
				<Card.Header>
					<Card.Title>
						{resultado.total} publicação(ões) entre {formatDateOnly(resultado.de)} e
						{formatDateOnly(resultado.ate)}
					</Card.Title>
					{#if resultado.truncado}
						<Card.Description class="text-amber-600">
							O DJEN tem mais resultados que o limite da busca. Reduza o período.
						</Card.Description>
					{/if}
				</Card.Header>
				<Card.Content class="space-y-4">
					{#if importaveis.length}
						<div class="flex flex-wrap items-end gap-3 rounded-md border p-3">
							<label class="flex items-center gap-2 text-sm">
								<Checkbox
									checked={marcados.length > 0 && marcados.length === importaveis.length}
									onCheckedChange={(v) => alternarTodos(v === true)}
								/>
								Marcar todas as que ainda não foram importadas ({importaveis.length})
							</label>
							<label class="flex items-center gap-2 text-sm">
								<Checkbox
									checked={paginaToda}
									disabled={importaveisDaPagina.length === 0}
									onCheckedChange={(v) => alternarPagina(v === true)}
								/>
								Marcar as desta página
							</label>
							<div class="min-w-60">
								<span class="mb-1 block text-sm font-medium">Parte dos processos novos</span>
								<Select.Root type="single" bind:value={parteId}>
									<Select.Trigger class="w-full" aria-label="Parte dos processos novos">
										{atendidos.find((a) => String(a.id) === parteId)?.nome ??
											'Escolha um atendido acima'}
									</Select.Trigger>
									<Select.Content>
										{#each atendidos as a (a.id)}
											<Select.Item value={String(a.id)}>{a.nome}</Select.Item>
										{/each}
									</Select.Content>
								</Select.Root>
							</div>
							<Button
								type="button"
								disabled={ocupado || marcados.length === 0 || (precisaParte && !parteId)}
								onclick={importar}
							>
								{importando ? 'Importando…' : `Importar selecionadas (${marcados.length})`}
							</Button>
							<Button
								type="button"
								variant="outline"
								disabled={ocupado || marcados.length === 0}
								onclick={marcarNaoPertinentes}
							>
								{marcandoNaoPertinentes
									? 'Marcando…'
									: `Descartar publicações (${marcados.length})`}
							</Button>
						</div>
						<p class="text-xs text-muted-foreground">
							Importar marca como relevante. As demais publicações continuam salvas para trabalhar
							depois.
						</p>
						{#if precisaParte && !parteId}
							<p class="text-sm text-amber-600">
								Há publicações de processos que ainda não existem no sistema: escolha um atendido
								(botão “Selecionar Atendidos”) para ser a parte dos processos criados.
							</p>
						{/if}
					{/if}

					{#if resultado.items.length === 0}
						<p class="text-sm text-muted-foreground">Nenhuma publicação encontrada.</p>
					{:else}
						<ul class="divide-y rounded-md border">
							{#each itensDaPagina as item (item.id_djen)}
								<li class="flex gap-3 p-3">
									<div class="pt-1">
										<Checkbox
											disabled={item.ja_no_banco}
											checked={marcados.includes(item.id_djen)}
											onCheckedChange={(v) => alternar(item.id_djen, v === true)}
											aria-label="Selecionar publicação {item.id_djen}"
										/>
									</div>
									<div class="min-w-0 flex-1 space-y-1">
										<div class="flex flex-wrap items-center gap-2 text-sm">
											<span class="font-medium">{formatDateOnly(item.data_disponibilizacao)}</span>
											<span class="font-mono">
												{item.numero_processo_mascara || item.numero_processo}
											</span>
											{#if item.sigla_tribunal}
												<Badge variant="outline">{item.sigla_tribunal}</Badge>
											{/if}
											{#if item.tipo_comunicacao}
												<span class="text-muted-foreground">{item.tipo_comunicacao}</span>
											{/if}

											{#if item.ja_no_banco}
												{#if item.publicacao_id}
													<a href="/djen/publicacoes/{item.publicacao_id}">
														<Badge>Já na tela operacional</Badge>
													</a>
												{:else}
													<Badge>Já na tela operacional</Badge>
												{/if}
											{/if}
											{#if item.processo_id}
												<a href="/processos/{item.processo_id}">
													<Badge variant="secondary">
														{item.processo_id_caso
															? `Processo do caso #${item.processo_id_caso}`
															: 'Processo sem caso'}
													</Badge>
												</a>
											{:else}
												<Badge variant="outline">Processo não cadastrado</Badge>
											{/if}
										</div>
										{#if item.nome_orgao}
											<p class="text-sm text-muted-foreground">{item.nome_orgao}</p>
										{/if}
										{#if item.destinatarios.length}
											<p class="text-xs text-muted-foreground">
												{item.destinatarios
													.map((d) => d.nome)
													.filter(Boolean)
													.join('; ')}
											</p>
										{/if}
										{#if item.resumo}
											<p class="line-clamp-3 text-sm">{item.resumo}</p>
										{/if}
										{#if item.link}
											<a
												href={item.link}
												target="_blank"
												rel="noopener noreferrer"
												class="text-xs text-primary hover:underline"
											>
												Abrir no tribunal
											</a>
										{/if}
									</div>
								</li>
							{/each}
						</ul>
						{#if totalPaginas > 1}
							<div class="flex items-center justify-between gap-3 text-sm">
								<span class="text-muted-foreground">
									{(pagina - 1) * POR_PAGINA + 1}–{Math.min(
										pagina * POR_PAGINA,
										resultado.items.length
									)} de {resultado.items.length}
								</span>
								<div class="flex items-center gap-2">
									<Button
										type="button"
										variant="outline"
										size="sm"
										disabled={pagina === 1}
										onclick={() => (pagina -= 1)}
									>
										<ChevronLeft class="h-4 w-4" />
										Anterior
									</Button>
									<span>Página {pagina} de {totalPaginas}</span>
									<Button
										type="button"
										variant="outline"
										size="sm"
										disabled={pagina === totalPaginas}
										onclick={() => (pagina += 1)}
									>
										Próxima
										<ChevronRight class="h-4 w-4" />
									</Button>
								</div>
							</div>
						{/if}
					{/if}
				</Card.Content>
			</Card.Root>
		{/if}
	{/if}
</div>
