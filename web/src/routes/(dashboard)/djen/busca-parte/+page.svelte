<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import * as Card from '$lib/components/ui/card';
	import * as Select from '$lib/components/ui/select';
	import Checkbox from '$lib/components/ui/checkbox/checkbox.svelte';
	import AtendidoSelectorDialog from '$lib/components/atendido-selector-dialog.svelte';
	import DateRangePicker from '$lib/components/date-range-picker.svelte';
	import { api } from '$lib/api-client';
	import { mensagemDeErro } from '$lib/utils/erros';
	import { formatDateOnly } from '$lib/utils/date';
	import { TRIBUNAIS_DJEN, MAX_TRIBUNAIS } from '$lib/utils/tribunais-djen';
	import { toast } from 'svelte-sonner';
	import {
		BUSCA_PARTE_MAX_DIAS,
		DJEN_PAPEIS_GESTAO,
		ROTULO_EXEMPLO_LABEL,
		type Atendido,
		type AtendidoNome,
		type ImportacaoBuscaParte,
		type NaoPertinentesBuscaParte,
		type ResultadoBuscaParte
	} from '$lib/types';
	import X from '@lucide/svelte/icons/x';
	import Search from '@lucide/svelte/icons/search';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
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
	semanaPassada.setDate(hoje.getDate() - 7);

	let nomes = $state<string[]>([]);
	let novoNome = $state('');
	let de = $state(isoLocal(semanaPassada));
	let ate = $state(isoLocal(hoje));
	let tribunais = $state<string[]>([]);

	// Atendidos escolhidos: fornecem nomes e a parte dos processos criados.
	let atendidosIds = $state<number[]>([]);
	let atendidos = $state<Atendido[]>([]);
	let parteId = $state('');

	let buscando = $state(false);
	let importando = $state(false);
	let marcandoNaoPertinentes = $state(false);
	const ocupado = $derived(importando || marcandoNaoPertinentes);
	let resultado = $state<ResultadoBuscaParte | null>(null);
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
		try {
			resultado = await api.get<ResultadoBuscaParte>(`djen/busca-parte?${parametros()}`);
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
			ids
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
				const lote = await api.post<NaoPertinentesBuscaParte>(
					'djen/busca-parte/nao-pertinentes',
					corpoDoLote(marcados.slice(i, i + LOTE_IMPORTACAO))
				);
				marcadas += lote.marcadas;
				naoEncontradas.push(...lote.nao_encontradas);
			}
			const partes = [`${marcadas} marcada(s) como não pertinente(s)`];
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

<div class="space-y-6">
	<div>
		<h1 class="text-3xl font-bold tracking-tight">Busca por parte no DJEN</h1>
		<p class="text-muted-foreground">
			Consulta direta ao DJEN pelo nome da parte. Nada é gravado até você importar ou marcar como
			não pertinente.
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
				<div>
					<label for="busca-periodo" class="mb-1 block text-sm font-medium">Período</label>
					<DateRangePicker id="busca-periodo" bind:de bind:ate maxDias={BUSCA_PARTE_MAX_DIAS} />
				</div>
				<div>
					<span class="mb-1 block text-sm font-medium">Tribunais</span>
					<Select.Root type="multiple" bind:value={tribunais}>
						<Select.Trigger class="w-56" aria-label="Tribunais">
							<span class="truncate">
								{tribunais.length === 0
									? 'Todos'
									: tribunais.length <= 3
										? tribunais.join(', ')
										: `${tribunais.length} tribunais`}
							</span>
						</Select.Trigger>
						<Select.Content class="max-h-80">
							{#each TRIBUNAIS_DJEN as grupo (grupo.grupo)}
								<Select.Group>
									<Select.GroupHeading>{grupo.grupo}</Select.GroupHeading>
									{#each grupo.siglas as sigla (sigla)}
										<Select.Item value={sigla}>{sigla}</Select.Item>
									{/each}
								</Select.Group>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>
				{#if tribunais.length > 0}
					<Button type="button" variant="ghost" size="sm" onclick={() => (tribunais = [])}>
						Limpar tribunais
					</Button>
				{/if}
				<Button type="submit" disabled={buscando}>
					<Search class="mr-2 h-4 w-4" />
					{buscando ? 'Consultando…' : 'Buscar no DJEN'}
				</Button>
			</div>
			<p class="text-xs text-muted-foreground">
				Período de até {BUSCA_PARTE_MAX_DIAS} dias, até {MAX_NOMES} nomes e até {MAX_TRIBUNAIS}
				tribunais por busca. Sem tribunal marcado, busca em todos.
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
								Marcar todas as que ainda não estão no sistema ({importaveis.length})
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
									: `Marcar como não pertinentes (${marcados.length})`}
							</Button>
						</div>
						<p class="text-xs text-muted-foreground">
							O que for importado ou marcado como não pertinente entra no banco de exemplos usado
							para treinar a sugestão automática. O que ficar sem marcação entra como “não revisada”
							e é apagado em 90 dias.
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
											{#if item.rotulo === 'pertinente' || item.rotulo === 'nao_pertinente'}
												<Badge
													variant={item.rotulo === 'pertinente' ? 'secondary' : 'outline'}
													class={item.rotulo === 'nao_pertinente'
														? 'border-amber-300 text-amber-800 dark:border-amber-700 dark:text-amber-200'
														: ''}
													title="Rótulo no banco de exemplos"
												>
													{ROTULO_EXEMPLO_LABEL[item.rotulo]}
												</Badge>
											{/if}
											{#if item.ja_no_banco}
												{#if item.publicacao_id}
													<a href="/djen/publicacoes/{item.publicacao_id}">
														<Badge>Já no sistema</Badge>
													</a>
												{:else}
													<Badge>Já no sistema</Badge>
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
